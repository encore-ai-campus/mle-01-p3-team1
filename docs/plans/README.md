# 구현 계획과 남은 확인

과거 계획은 현재 사용법을 보장하지 않습니다. 완료 여부가 확정되지 않은 계획은 유지합니다. 일부 파일이 존재한다는 이유만으로 모든 작업을 완료로 표시하지 않습니다.

| 계획 | 현재 판정 |
|---|---|
| [BM25 계획](2026-11-13-museum-bm25-hybrid.md) | Graph 확장을 포함한 당시 계획. 현재 src/hybrid의 Vector+BM25 서비스와 다르므로 완료로 분류하지 않음 |
| [사용자 안내](2026-11-13-repository-user-guide.md) | 이번 문서 정리와 겹침. 원래 체크리스트 전체 충족 여부는 확인 보류 |
| [Supervisor 연결](2026-11-13-supervisor-hybrid-integration.md) | 연결 코드 존재. 원 계획 전체와 실환경 검증 완료 여부는 구분 필요 |
| [Supervisor 컨텍스트](2026-11-14-supervisor-context.md) | 관련 구현 존재. 현재 라우팅 규칙과 대조하며 잔여 항목 관리 |
| [Neo4j 적재](neo4j-load-implementation-plan.md) | 적재 보고서 존재. 당시 계획 전체 완료 판정은 보류 |

완료 체크와 구현이 대응하는 병렬 평가·지역 별칭 계획은 [보관 폴더](../archive/plans/README.md)에 있습니다. 기술 선택의 이유는 [decisions](../decisions/README.md), 실제 작업 결과는 [records](../records/README.md)에 둡니다.
