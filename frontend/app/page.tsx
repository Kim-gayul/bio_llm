"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  Dna,
  ExternalLink,
  FlaskConical,
  Menu,
  MessageSquare,
  Microscope,
  Plus,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Source = {
  pmcid: string;
  title: string;
  text: string;
  chunk_id: string;
  url: string;
  distance: number;
};
type Message = {
  id?: number;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  status: string;
  warnings?: string[];
};
type Conversation = { id: string; title: string };
type Paper = {
  pmcid: string;
  title: string;
  abstract: string;
  url: string;
  chunk_count: number;
  raw_methods_full?: string;
};
type Health = {
  model: string;
  ollama: boolean;
  index: boolean;
  chunks: number;
};
type StreamEvent = {
  type: string;
  text?: string;
  message?: string;
  sources?: Source[];
  warnings?: string[];
};
const suggestions = [
  {
    icon: FlaskConical,
    tag: "실험 조건 이해",
    title: "CRISPR-Cas9, 어디서 시작할까요?",
    question:
      "논문에 나온 CRISPR-Cas9 실험 조건을 신입생 눈높이로 설명해 주세요.",
    color: "purple",
  },
  {
    icon: Microscope,
    tag: "프로토콜 비교",
    title: "Transfection 조건을 비교하고 싶어요",
    question:
      "검색된 논문들의 Transfection 조건을 각각 구분해서 비교해 주세요. 없는 조건은 없다고 표시해 주세요.",
    color: "blue",
  },
  {
    icon: BookOpen,
    tag: "논문 읽기",
    title: "Methods를 쉽게 풀어 주세요",
    question:
      "검색된 논문의 Methods에서 핵심 실험 목적과 조건, 신입생이 확인해야 할 점을 설명해 주세요.",
    color: "green",
  },
];

export default function Workspace() {
  const [tab, setTab] = useState<"chat" | "papers">("chat");
  const [csrf, setCsrf] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [question, setQuestion] = useState("");
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("");
  const [topK, setTopK] = useState(2);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Paper | Source | null>(null);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const sending = useRef(false);

  async function api(path: string, options: RequestInit = {}) {
    const response = await fetch(`/api/${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
        ...options.headers,
      },
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(
        data.error ||
          "서버에 연결할 수 없습니다. Django 실행 상태를 확인해 주세요.",
      );
    }
    return response;
  }

  async function refreshHealth() {
    try {
      setHealth(await (await api("health/")).json());
    } catch {
      setHealth(null);
    }
  }

  async function initialize() {
    setError("");
    try {
      const session = await (await api("session/")).json();
      setCsrf(session.csrfToken);
      const [history, library] = await Promise.all([
        api("conversations/").then((r) => r.json()),
        api("papers/").then((r) => r.json()),
      ]);
      setConversations(history.conversations);
      setPapers(library.papers);
      await refreshHealth();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void initialize();
  }, []); // Initialize a same-origin session once on mount.
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  async function openConversation(id: string) {
    if (busy || loading) return;
    setLoading(true);
    setError("");
    try {
      const data = await (await api(`conversations/${id}/`)).json();
      setActive(id);
      setMessages(data.messages);
      setTab("chat");
      setMobileMenu(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function newConversation() {
    setActive(null);
    setMessages([]);
    setQuestion("");
    setError("");
    setScope("");
    setTab("chat");
    setMobileMenu(false);
  }

  async function send(event?: FormEvent) {
    event?.preventDefault();
    if (sending.current || !question.trim() || !csrf || loading) return;
    sending.current = true;
    setBusy(true);
    setError("");
    setStatus("논문을 살펴볼 준비를 하고 있어요.");
    const text = question.trim();
    let id = active;
    let started = false;
    try {
      if (!id) {
        const created = await (
          await api("conversations/", { method: "POST" })
        ).json();
        id = created.id;
        setActive(id);
        setConversations((previous) => [
          { id: created.id, title: text.slice(0, 80) },
          ...previous,
        ]);
      }
      const response = await api(`conversations/${id}/messages/`, {
        method: "POST",
        body: JSON.stringify({
          question: text,
          top_k: topK,
          pmcid: scope || null,
        }),
      });
      if (!response.body) throw new Error("스트리밍 응답을 읽을 수 없습니다.");
      started = true;
      setQuestion("");
      setMessages((previous) => [
        ...previous,
        { role: "user", content: text, sources: [], status: "complete" },
        { role: "assistant", content: "", sources: [], status: "pending" },
      ]);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "",
        completed = false;
      function consume(packet: StreamEvent) {
        if (packet.type === "status") setStatus(packet.message || "");
        if (packet.type === "error") throw new Error(packet.message);
        if (packet.type === "done") {
          completed = true;
          setStatus("");
        }
        if (["token", "sources", "done"].includes(packet.type)) {
          if (packet.type === "token") setStatus("");
          setMessages((previous) =>
            previous.map((message, index) =>
              index === previous.length - 1
                ? {
                    ...message,
                    content:
                      message.content +
                      (packet.type === "token" ? packet.text || "" : ""),
                    sources: packet.sources ?? message.sources,
                    status:
                      packet.type === "done" ? "complete" : message.status,
                    warnings: packet.warnings ?? message.warnings,
                  }
                : message,
            ),
          );
        }
      }
      try {
        while (true) {
          const { value, done } = await reader.read();
          buffer += decoder.decode(value, { stream: !done });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) if (line.trim()) consume(JSON.parse(line));
          if (done) break;
        }
        if (buffer.trim()) consume(JSON.parse(buffer));
        if (!completed)
          throw new Error(
            "연결이 끊어졌습니다. 대화를 다시 열어 저장 상태를 확인해 주세요.",
          );
      } finally {
        reader.releaseLock();
      }
    } catch (e) {
      setError((e as Error).message);
      if (started)
        setMessages((previous) =>
          previous.map((message, index) =>
            index === previous.length - 1
              ? { ...message, status: "failed" }
              : message,
          ),
        );
    } finally {
      sending.current = false;
      setBusy(false);
      setStatus("");
      void refreshHealth();
      if (id)
        api("conversations/")
          .then((r) => r.json())
          .then((data) => setConversations(data.conversations))
          .catch(() => {});
    }
  }

  async function deleteConversation() {
    if (!active) return;
    try {
      await api(`conversations/${active}/`, { method: "DELETE" });
      setConversations((previous) =>
        previous.filter((item) => item.id !== active),
      );
      newConversation();
    } catch (e) {
      setError((e as Error).message);
    }
    setConfirmDelete(false);
  }

  function download() {
    const content = messages
      .map(
        (m) =>
          `## ${m.role === "user" ? "질문" : "AI 선배"}\n\n${m.content}\n\n${m.sources.map((s) => `- [${s.pmcid}] ${s.title}\n  ${s.url}`).join("\n")}`,
      )
      .join("\n\n---\n\n");
    const url = URL.createObjectURL(
      new Blob([content], { type: "text/markdown;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "biolab-research-notes.md";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function viewPaper(paper: Paper) {
    try {
      setSelected(await (await api(`papers/${paper.pmcid}/`)).json());
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const ready = health?.ollama && health?.index;
  const filtered = papers.filter((p) =>
    `${p.title} ${p.pmcid} ${p.abstract}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const lastSources =
    [...messages].reverse().find((m) => m.sources.length)?.sources || [];

  return (
    <div className="workspace">
      {mobileMenu && (
        <button
          className="scrim"
          aria-label="메뉴 닫기"
          onClick={() => setMobileMenu(false)}
        />
      )}
      <aside className={`sidebar ${mobileMenu ? "open" : ""}`}>
        <a className="brand" href="/">
          <span className="brand-icon">
            <Dna size={25} />
          </span>
          BioLab<span className="brand-dot">.</span>
        </a>
        <div className="workspace-label">MY RESEARCH WORKSPACE</div>
        <button
          className="new-chat"
          disabled={busy || loading}
          onClick={newConversation}
        >
          <Plus size={18} />새 연구 대화
        </button>
        <nav aria-label="주요 메뉴">
          <button
            className={tab === "chat" ? "nav-item active" : "nav-item"}
            onClick={() => {
              setTab("chat");
              setMobileMenu(false);
            }}
          >
            <MessageSquare size={18} />
            AI 선배와 대화<span className="tiny-badge">AI</span>
          </button>
          <button
            className={tab === "papers" ? "nav-item active" : "nav-item"}
            onClick={() => {
              setTab("papers");
              setMobileMenu(false);
            }}
          >
            <BookOpen size={18} />
            논문 라이브러리<span className="nav-count">{papers.length}</span>
          </button>
        </nav>
        <div className="history-label">
          최근 연구 대화 <span>{conversations.length}</span>
        </div>
        <div className="history-list">
          {conversations.length === 0 ? (
            <p className="empty-history">
              첫 질문으로 연구 기록을
              <br />
              시작해 보세요.
            </p>
          ) : (
            conversations.map((item) => (
              <button
                key={item.id}
                disabled={busy || loading}
                className={
                  active === item.id ? "history-item selected" : "history-item"
                }
                onClick={() => void openConversation(item.id)}
              >
                <MessageSquare size={14} />
                <span>{item.title}</span>
              </button>
            ))
          )}
        </div>
        <div className="privacy-card">
          <ShieldCheck size={20} />
          <strong>연구는 나의 공간에서</strong>
          <p>
            질문과 AI 추론은 로컬에서.
            <br />
            연구 대화는 내 컴퓨터에 저장돼요.
          </p>
          <span>
            <i />
            LOCAL FIRST
          </span>
        </div>
        <div className="profile">
          <div className="avatar">R</div>
          <div>
            <strong>나의 연구 공간</strong>
            <small>석사 신입생 · Researcher</small>
          </div>
          <span className="profile-dot" />
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-only"
              aria-label="메뉴 열기"
              onClick={() => setMobileMenu(true)}
            >
              <Menu size={20} />
            </button>
            <span>연구 공간</span>
            <ChevronRight size={14} />
            <strong>
              {tab === "chat" ? "AI 선배와 대화" : "논문 라이브러리"}
            </strong>
          </div>
          <button
            className={`connection ${ready ? "ready" : ""}`}
            onClick={() => void refreshHealth()}
            title="클릭하여 연결 상태 새로고침"
          >
            <i />
            {ready ? "로컬 AI 연결됨" : "연결 상태 확인"}
          </button>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button onClick={() => void initialize()}>연결 재확인</button>
            <button
              className="icon-button"
              aria-label="오류 닫기"
              onClick={() => setError("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {tab === "chat" ? (
          <div className="chat-layout">
            <section className="chat-main">
              <div className="chat-scroll">
                {!messages.length ? (
                  <div className="welcome">
                    <div className="eyebrow">
                      <span />
                      YOUR FIRST RESEARCH PARTNER
                    </div>
                    <h1>
                      처음 시작하는 연구,
                      <br />
                      <span>든든한 선배와 함께.</span>
                    </h1>
                    <p className="intro">
                      낯선 논문부터 복잡한 실험 조건까지.
                      <br />
                      논문 속 근거를 함께 읽고, 다음 연구를 준비해요.
                    </p>
                    <div className="trust-row">
                      <span>
                        <BookOpen size={14} />
                        PMC 논문 기반
                      </span>
                      <span>
                        <ShieldCheck size={14} />
                        로컬 AI
                      </span>
                      <span>
                        <Check size={14} />
                        출처와 함께 설명
                      </span>
                    </div>
                    <div className="suggestion-heading">
                      어떤 연구를 도와드릴까요?<span>이렇게 질문해 보세요</span>
                    </div>
                    <div className="suggestions">
                      {suggestions.map(({ icon: Icon, ...item }) => (
                        <button
                          key={item.tag}
                          className="suggestion"
                          onClick={() => setQuestion(item.question)}
                        >
                          <span className={`suggestion-icon ${item.color}`}>
                            <Icon size={20} />
                          </span>
                          <small>{item.tag}</small>
                          <strong>{item.title}</strong>
                          <span className="suggestion-arrow">
                            <ArrowRight size={16} />
                          </span>
                        </button>
                      ))}
                    </div>
                    <div className="welcome-note">
                      <Sparkles size={16} />
                      <span>
                        좋은 질문은 좋은 연구의 시작이에요. 작은 궁금증도
                        괜찮아요.
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="messages">
                    <div className="conversation-toolbar">
                      <span>나의 연구 대화</span>
                      <div>
                        <button disabled={busy} onClick={download}>
                          <ArrowDownToLine size={15} />
                          내보내기
                        </button>
                        <button
                          disabled={busy}
                          aria-label="현재 대화 삭제"
                          onClick={() => setConfirmDelete(true)}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                    {messages.map((message, index) => (
                      <article
                        key={
                          message.id ? `saved-${message.id}` : `new-${index}`
                        }
                        className={`message ${message.role}`}
                      >
                        <div className="message-avatar">
                          {message.role === "assistant" ? (
                            <Dna size={19} />
                          ) : (
                            "나"
                          )}
                        </div>
                        <div className="message-body">
                          <div className="message-label">
                            {message.role === "assistant"
                              ? "AI 사수 선배"
                              : "나"}
                            {message.role === "assistant" && (
                              <span>논문 기반</span>
                            )}
                          </div>
                          <div className="markdown">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                a: ({ href, children }) => (
                                  <a
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    {children}
                                  </a>
                                ),
                                img: () => null,
                              }}
                            >
                              {message.content}
                            </ReactMarkdown>
                          </div>
                          {message.status === "pending" && (
                            <div className="thinking" role="status">
                              <span className="pulse" />
                              {status || "답변을 작성하고 있어요…"}
                            </div>
                          )}
                          {message.status === "failed" && (
                            <p className="message-warning">
                              답변이 완료되지 않았습니다. 연결을 확인하고 다시
                              질문해 주세요.
                            </p>
                          )}
                          {message.warnings?.map((w) => (
                            <p className="message-warning" key={w}>
                              {w}
                            </p>
                          ))}
                          {message.sources.length > 0 && (
                            <div className="source-chips">
                              {message.sources.map((source, i) => (
                                <button
                                  key={source.chunk_id}
                                  onClick={() => setSelected(source)}
                                >
                                  <BookOpen size={12} />
                                  {i + 1}. {source.pmcid}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </article>
                    ))}
                    <div ref={bottom} />
                  </div>
                )}
              </div>
              <div className="composer-area">
                <form className="composer" onSubmit={send}>
                  <label className="sr-only" htmlFor="question">
                    연구 질문
                  </label>
                  <textarea
                    id="question"
                    value={question}
                    maxLength={4000}
                    disabled={busy || loading}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="실험이나 논문에 대해 궁금한 점을 물어보세요…"
                    rows={2}
                    onKeyDown={(e) => {
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing
                      ) {
                        e.preventDefault();
                        void send();
                      }
                    }}
                  />
                  <div className="composer-bottom">
                    <span>
                      <ShieldCheck size={13} />
                      로컬 연구 공간
                    </span>
                    <span className="input-hint">
                      {question.length > 3500
                        ? `${question.length}/4,000`
                        : "Shift + Enter 줄바꿈"}
                    </span>
                    <button
                      className="send-button"
                      aria-label="질문 보내기"
                      disabled={busy || loading || !csrf || !question.trim()}
                      type="submit"
                    >
                      <Send size={17} />
                    </button>
                  </div>
                </form>
                <p className="composer-caption">
                  AI 답변은 논문 이해를 돕는 참고 자료입니다. 실제 실험 전
                  원문과 연구실 SOP를 확인해 주세요.
                </p>
              </div>
            </section>
            <aside className="context-panel">
              <div className="panel-heading">
                <BookOpen size={17} />
                <strong>연구 컨텍스트</strong>
              </div>
              <p className="panel-description">
                답변의 바탕이 되는 논문과
                <br />
                AI 연결 상태를 확인하세요.
              </p>
              <div className="context-card">
                <span className="section-kicker">REFERENCE LIBRARY</span>
                <div className="library-number">
                  {papers.length}
                  <small>편의 논문</small>
                </div>
                <div className="library-detail">PubMed Central · Methods</div>
                <button
                  className="text-button"
                  onClick={() => setTab("papers")}
                >
                  라이브러리 살펴보기
                  <ArrowRight size={14} />
                </button>
              </div>
              <div className="settings">
                <label htmlFor="scope">검색 범위</label>
                <select
                  id="scope"
                  value={scope}
                  disabled={busy}
                  onChange={(e) => setScope(e.target.value)}
                >
                  <option value="">전체 논문</option>
                  {papers.map((p) => (
                    <option key={p.pmcid} value={p.pmcid}>
                      {p.pmcid}
                    </option>
                  ))}
                </select>
                <label htmlFor="top-k">참조할 문단 수</label>
                <select
                  id="top-k"
                  value={topK}
                  disabled={busy}
                  onChange={(e) => setTopK(Number(e.target.value))}
                >
                  {[1, 2, 3, 4, 5, 6].map((n) => (
                    <option key={n} value={n}>
                      {n}개 문단{n === 2 ? " · 기본" : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div className="sources-panel">
                <h3>이번 대화의 근거</h3>
                {lastSources.length ? (
                  lastSources.map((source, i) => (
                    <button
                      className="source-card"
                      key={source.chunk_id}
                      onClick={() => setSelected(source)}
                    >
                      <span>
                        0{i + 1} · {source.pmcid}
                      </span>
                      <strong>{source.title}</strong>
                      <small>
                        원문 발췌 보기 <ArrowRight size={12} />
                      </small>
                    </button>
                  ))
                ) : (
                  <div className="sources-empty">
                    <BookOpen size={25} />
                    <p>
                      질문을 보내면
                      <br />
                      참고한 논문이 여기에 표시돼요.
                    </p>
                  </div>
                )}
              </div>
              <div className="model-status">
                <div>
                  <span
                    className={health?.ollama ? "status-dot ok" : "status-dot"}
                  />
                  Ollama 모델<span>{health?.ollama ? "연결됨" : "미연결"}</span>
                </div>
                <div>
                  <span
                    className={health?.index ? "status-dot ok" : "status-dot"}
                  />
                  논문 인덱스
                  <span>
                    {health?.index ? `${health.chunks}개 청크` : "준비 필요"}
                  </span>
                </div>
                <p>{health?.model || "Django 연결을 확인해 주세요"}</p>
                {!ready && (
                  <details>
                    <summary>시작 안내</summary>
                    <p>
                      README 순서대로 모델을 준비하고 인덱스를 구축하세요.
                      Ollama와 Django를 실행한 뒤 상단 연결 상태를 눌러 주세요.
                    </p>
                  </details>
                )}
              </div>
            </aside>
          </div>
        ) : (
          <section className="library">
            <div className="eyebrow">YOUR REFERENCE LIBRARY</div>
            <h1>
              논문 라이브러리<span>{papers.length}</span>
            </h1>
            <p className="intro">
              실험의 근거를 직접 읽고, AI 선배와 함께 이해해 보세요.
            </p>
            <label className="library-search">
              <Search size={18} />
              <input
                aria-label="논문 검색"
                placeholder="논문 제목, PMCID 또는 초록 검색"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <div className="paper-grid">
              {filtered.map((p) => (
                <article className="paper-card" key={p.pmcid}>
                  <div className="paper-meta">
                    <span>{p.pmcid}</span>
                    <span>METHODS · {p.chunk_count} 문단</span>
                  </div>
                  <h2>{p.title}</h2>
                  <p>
                    {p.abstract ||
                      "초록이 없는 논문입니다. Methods 원문을 확인해 주세요."}
                  </p>
                  <div className="paper-actions">
                    <button onClick={() => void viewPaper(p)}>
                      논문 살펴보기
                      <ArrowRight size={14} />
                    </button>
                    <button
                      disabled={busy}
                      onClick={() => {
                        setScope(p.pmcid);
                        setQuestion(
                          "선택한 논문의 Methods 핵심을 설명해 주세요.",
                        );
                        setTab("chat");
                      }}
                    >
                      이 논문으로 질문
                    </button>
                  </div>
                </article>
              ))}
            </div>
            {!filtered.length && (
              <div className="library-empty">
                <BookOpen size={30} />
                <h2>
                  {query
                    ? "검색 결과가 없습니다"
                    : "아직 준비된 논문이 없습니다"}
                </h2>
                <p>
                  {query
                    ? "다른 키워드나 PMCID로 검색해 보세요."
                    : "데이터 수집과 전처리를 실행하면 논문이 표시됩니다."}
                </p>
              </div>
            )}
          </section>
        )}
      </main>
      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <section
            className="detail-modal"
            role="dialog"
            aria-modal="true"
            aria-label="논문 근거"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape") setSelected(null);
            }}
          >
            <button
              autoFocus
              className="modal-close icon-button"
              aria-label="닫기"
              onClick={() => setSelected(null)}
            >
              <X size={20} />
            </button>
            <div className="eyebrow">{selected.pmcid} · PAPER EVIDENCE</div>
            <h2>{selected.title}</h2>
            <a
              className="external-link"
              href={selected.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              PMC 원문 열기
              <ExternalLink size={14} />
            </a>
            {"text" in selected ? (
              <>
                <h3>검색된 Methods 발췌</h3>
                <p className="original-text">{selected.text}</p>
                <small className="muted">
                  {selected.chunk_id} · cosine distance {selected.distance}{" "}
                  (신뢰도 점수가 아닙니다)
                </small>
              </>
            ) : (
              <>
                <h3>Abstract</h3>
                <p className="original-text">
                  {selected.abstract || "초록 없음"}
                </p>
                <h3>Materials & Methods</h3>
                <p className="original-text">
                  {selected.raw_methods_full || "Methods 원문 없음"}
                </p>
              </>
            )}
          </section>
        </div>
      )}
      {confirmDelete && (
        <div className="modal-backdrop">
          <section
            className="confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-label="대화 삭제 확인"
          >
            <h2>이 대화를 삭제할까요?</h2>
            <p>저장된 질문과 답변이 함께 삭제됩니다.</p>
            <div>
              <button autoFocus onClick={() => setConfirmDelete(false)}>
                취소
              </button>
              <button
                className="danger"
                onClick={() => void deleteConversation()}
              >
                삭제
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
