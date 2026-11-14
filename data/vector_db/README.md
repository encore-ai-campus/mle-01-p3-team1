# 로컬 Chroma DB

`museum_chroma/`는 `museum_documents` 컬렉션을 보관하는 로컬 DB입니다. SQLite 파일과 인덱스 파일이 함께 필요합니다. Git에 일부 파일만 추적될 수 있으므로 새 클론에서는 완전한 DB를 별도로 받거나 [구축 노트북](../../notebooks/README.md)을 사용하세요. 현재 사용하는 DB가 있을 때는 덮어쓰기 전에 백업하고 실행 중인 평가를 종료해야 합니다.
