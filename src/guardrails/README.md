# 입력·출력 가드레일

`guard.py`는 개인정보 정규식 및 NeMo Guardrails 검사, `config/`는 규칙과 판정 프롬프트를 포함합니다. 연결된 Supervisor는 검색 전 입력과 최종 답변을 검사합니다. Streamlit UI는 별도로 같은 가드레일을 호출합니다. 검사 오류 시 차단합니다.

[가드레일 평가셋](../../evaluations/datasets/guardrails/가드레일_평가_v1.md)은 질문과 기대 결과이며, `eval_guardrails.py`는 **Streamlit UI 경로** 평가 코드입니다. 실행 결과는 `outputs/evaluation/guardrails/run_<시각>/report.md`에 저장됩니다. 기존 결과는 [평가 결과 이력](../../evaluations/reports/guardrails/README.md)에 있습니다. 실제 평가에는 OpenAI API 사용료가 발생할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m src.guardrails.eval_guardrails
```


## 가드레일 설정

`config.yml`은 모델과 개인정보 정규식, `prompts.yml`은 LLM 판정 프롬프트를 정의합니다. `GUARDRAILS_MODEL` 환경변수로 모델을 선택할 수 있습니다. 사용법은 [상위 안내](README.md)를 참고하세요.
