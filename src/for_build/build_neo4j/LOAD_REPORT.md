# Neo4j 박물관 적재 보고서

**실행일:** 2026-11-12 (KST)  
**입력:** `src/for_build/museum_final_738.csv`  
**입력 SHA-256:** `c40d1f2d794bfd6415c763fe487d639a634c0cba9313984ec4b0b67a4ea6cb45`  
**환경:** Python 3.12.13, Neo4j Python Driver 6.4.1, 대상 DB `878d9ed6`  
**상태:** 적재 후 Neo4j에서 읽은 수가 입력 기준과 일치함. 동일 CSV를 재실행한 뒤에도 수가 유지됨.

| 대상 | CSV에서 예상 | Neo4j 읽기 결과 |
|---|---:|---:|
| 박물관 `Museum` | 738 | 738 |
| 출처 `SourceDocument` | 1,027 | 1,027 |
| 본문 구간 `TextSpan` | 3,260 | 3,260 |
| `Museum`–`SourceDocument` | 1,027 | 1,027 |
| `Museum`–`TextSpan` | 3,260 | 3,260 |
| `TextSpan`–`SourceDocument` | 3,270 | 3,270 |
| 시도 `Sido` | 20 | 20 |
| 시군구 `Sigungu` (시도+시군구 조합) | 199 | 199 |
| `Museum`–`Sigungu` | 738 | 738 |
| `Sigungu`–`Sido` | 199 | 199 |

적재는 박물관 50개씩 15개 트랜잭션으로 실행했습니다. 입력 전체의 ID 중복, JSON 구조, 본문 길이·SHA-256, 좌표, 근거 구간과 출처 참조를 쓰기 전에 검증했습니다. Python 3.12 테스트 10개가 통과했습니다. 정확한 기계 판독 결과는 `load_result.json`을 확인합니다.

## 데이터 품질과 후속 작업

- 655개 박물관에 `requires_manual_review=True`가 설정되어 있습니다. `adult_fee=0`인 428개 행의 상태는 `BASE_FEE_ZERO_CHECK_EXCEPTIONS`입니다. 검증 없이 무료로 안내하지 않아야 합니다.
- 출처 메타데이터가 가리키는 `museum_base_1070.csv`와 `web_research_verified.csv`는 현재 저장소에 없습니다. 이 출처의 원문 대조는 수행하지 못했습니다. 출처 메타데이터와 근거 구간은 그래프에 보존했습니다.
- 임베딩, 벡터 인덱스, 1차 벡터 검색은 아직 구성하지 않았습니다. 모델과 차원이 지정되지 않아 **알 수 없음**이며, 별도 벡터 작업에서 정한 후 2단계 GraphRAG 검색을 연결해야 합니다.
- 실행 전 DB의 같은 ID 데이터 수는 기록하지 않았으므로, 위 숫자를 모두 이번 실행에서 새로 생성한 수로 해석할 수 없습니다. 이 보고서는 현재 DB의 읽기 검증 결과를 나타냅니다.
