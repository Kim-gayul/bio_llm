import json
import logging
import re
import threading
from time import perf_counter

from django.db import close_old_connections
from django.http import JsonResponse, StreamingHttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods, require_GET

from biolab import rag
from biolab.config import OPENAI_API_KEY, OPENAI_MODEL
from biolab.papers import load_papers, paper_summary
from .models import Conversation, Message

logger = logging.getLogger(__name__)
# One generation at a time; run one backend worker for this personal deployment.
generation_lock = threading.Lock()


def body(request):
    try:
        data = json.loads(request.body)
        return data if isinstance(data, dict) else {}
    except (ValueError, UnicodeDecodeError):
        return {}


def owned(request, pk):
    return get_object_or_404(Conversation, pk=pk, session_key=request.session.session_key or "")


def serialize_message(message):
    return {"id": message.id, "role": message.role, "content": message.content,
        "sources": message.sources, "status": message.status,
        "warnings": citation_warnings(message.content, message.sources) if message.role == "assistant" and message.status == "complete" else []}


def citation_warnings(content, sources):
    cited = set(re.findall(r"\[(PMC\d+)\]", content))
    allowed = {source["pmcid"] for source in sources}
    warnings = []
    if cited - allowed:
        warnings.append("답변에 검색 근거에 없는 PMCID가 포함되어 있습니다. 원문을 확인해 주세요.")
    if sources and not cited:
        warnings.append("답변에 문장별 출처가 없습니다. 아래 검색 근거를 직접 확인해 주세요.")
    return warnings


@require_GET
def session(request):
    if not request.session.session_key:
        request.session.create()
    return JsonResponse({"csrfToken": get_token(request)})


@require_GET
def health(request):
    # Configuration status only: no paid request and no API key in the response.
    result = {"model": OPENAI_MODEL, "openai_configured": bool(OPENAI_API_KEY),
              "index": False, "chunks": 0}
    try:
        result["chunks"] = rag.collection().count()
        result["index"] = result["chunks"] > 0
    except Exception:
        pass
    # Do not load multi-GB models on a status request. Cache availability is verified by a real query.
    return JsonResponse(result)


@require_GET
def papers(request):
    query = request.GET.get("q", "").casefold()[:200]
    result = [paper_summary(p) for p in load_papers() if query in (p["title"] + p["pmcid"] + p.get("abstract", "")).casefold()]
    return JsonResponse({"papers": result})


@require_GET
def paper(request, pmcid):
    for item in load_papers():
        if item["pmcid"] == pmcid:
            return JsonResponse(item)
    return JsonResponse({"error": "논문을 찾을 수 없습니다."}, status=404)


@require_http_methods(["GET", "POST"])
def conversations(request):
    if not request.session.session_key:
        request.session.create()
    if request.method == "POST":
        item = Conversation.objects.create(session_key=request.session.session_key)
        return JsonResponse({"id": str(item.id), "title": item.title}, status=201)
    items = Conversation.objects.filter(session_key=request.session.session_key).order_by("-updated_at")
    return JsonResponse({"conversations": list(items.values("id", "title", "updated_at"))})


@require_http_methods(["GET", "DELETE"])
def conversation(request, pk):
    item = owned(request, pk)
    if request.method == "DELETE":
        if not generation_lock.acquire(blocking=False):
            return JsonResponse({"error": "답변 완료 후 대화를 삭제해 주세요."}, status=409)
        try:
            item.delete()
        finally:
            generation_lock.release()
        return JsonResponse({"deleted": True})
    return JsonResponse({"id": str(item.id), "title": item.title,
        "messages": [serialize_message(m) for m in item.messages.all()]})


def event(kind, **payload):
    return json.dumps({"type": kind, **payload}, ensure_ascii=False) + "\n"


@require_http_methods(["POST"])
def chat(request, pk):
    item = owned(request, pk)
    data = body(request)
    question = data.get("question", "")
    top_k = data.get("top_k", 2)
    pmcid = data.get("pmcid")
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
        return JsonResponse({"error": "질문은 1~4,000자로 입력해 주세요."}, status=400)
    if type(top_k) is not int or not 1 <= top_k <= 6:
        return JsonResponse({"error": "검색 청크 수는 1~6이어야 합니다."}, status=400)
    if pmcid is not None and (not isinstance(pmcid, str) or not re.fullmatch(r"PMC\d+", pmcid)):
        return JsonResponse({"error": "올바른 PMCID가 필요합니다."}, status=400)
    if not generation_lock.acquire(blocking=False):
        return JsonResponse({"error": "다른 답변을 생성 중입니다. 잠시 후 다시 시도해 주세요."}, status=409)
    try:
        history = list(item.messages.filter(status="complete").order_by("-id").values("role", "content")[:6])[::-1]
        question = question.strip()
        Message.objects.create(conversation=item, role="user", content=question)
        assistant = Message.objects.create(conversation=item, role="assistant", status="pending")
        if item.title == "새 연구 대화":
            item.title = question[:80]
        item.save()
    except Exception:
        generation_lock.release()
        raise

    def stream():
        chunks, sources = [], []
        status = "failed"
        started = perf_counter()
        timings = {}
        try:
            yield event("status", message="질문을 정리하고 논문 근거를 찾고 있어요.")
            sources = rag.retrieve(question, history, top_k, pmcid, timings=timings)
            timings["retrieval_ms"] = round((perf_counter() - started) * 1000, 1)
            yield event("sources", sources=sources)
            answer_started = perf_counter()
            for token in rag.answer(question, history, sources):
                if not chunks:
                    timings["first_text_ms"] = round((perf_counter() - started) * 1000, 1)
                    timings["answer_first_text_ms"] = round((perf_counter() - answer_started) * 1000, 1)
                chunks.append(token)
                yield event("token", text=token)
            timings["answer_ms"] = round((perf_counter() - answer_started) * 1000, 1)
            content = "".join(chunks)
            if not content.strip():
                raise RuntimeError("Empty model answer")
            warnings = citation_warnings(content, sources)
            assistant.content, assistant.sources, assistant.status = content, sources, "complete"
            assistant.save(update_fields=["content", "sources", "status"])
            status = "complete"
            timings["total_ms"] = round((perf_counter() - started) * 1000, 1)
            yield event("done", message_id=assistant.id, warnings=warnings, timings=timings)
        except GeneratorExit:
            raise
        except Exception as exc:
            # Provider error bodies can contain credential fragments; log only the type.
            logger.error("RAG generation failed (%s)", type(exc).__name__)
            yield event("error", message="답변 생성에 실패했습니다. OpenAI API 키·모델 접근 권한·사용 한도와 임베딩 캐시·인덱스를 확인해 주세요.")
        finally:
            try:
                if status != "complete":
                    assistant.content = "".join(chunks)
                    assistant.sources = sources
                    assistant.status = "failed"
                    assistant.save(update_fields=["content", "sources", "status"])
            finally:
                generation_lock.release()
                close_old_connections()

    response = StreamingHttpResponse(stream(), content_type="application/x-ndjson; charset=utf-8")
    response["Cache-Control"] = "no-cache, no-store"
    response["X-Accel-Buffering"] = "no"
    return response
