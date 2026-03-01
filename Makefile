.PHONY: dev rag infra all down status

dev:  ## Core infra only (postgres + redis) for basic development
	docker compose --profile core up -d

rag:  ## Full RAG infra (postgres + redis + minio + qdrant)
	docker compose --profile core --profile rag up -d

infra: rag  ## Alias for 'rag'

all:  ## Full stack containerized (all services + build)
	docker compose --profile core --profile rag --profile app up -d --build

down:  ## Stop all services
	docker compose --profile core --profile rag --profile app down

status:  ## Show running services
	docker compose --profile core --profile rag --profile app ps
