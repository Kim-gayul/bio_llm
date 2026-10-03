# BioLab 홍보영상

`output/BioLab-promo-30s-1080p.mp4`는 30초, 1920×1080 H.264/AAC 영상입니다. 자막과 포스터도 함께 들어 있습니다. 영상 속 논문 카드와 대화는 기능을 보여주는 **연출 화면**이며 실제 논문 본문이나 실제 LLM 응답을 사용하지 않았습니다.

`render.py`는 Windows의 Malgun Gothic/Segoe UI 폰트와 FFmpeg를 사용합니다. 외부 음원이나 폰트 파일은 저장소에 포함하지 않습니다.

```powershell
uv pip install --python .\.venv\Scripts\python.exe -r promo/requirements.txt
.\.venv\Scripts\python.exe promo/render.py
```

다른 운영체제에서는 `render.py`의 폰트 경로를 설치된 한글 폰트로 바꾸세요.
