# Smart Load Protection Panel — Developer Makefile

.PHONY: help start test test-backend test-firmware benchmarks migrate build-dashboard clean

help:
	@echo "Available commands:"
	@echo "  make start            - Start full stack using PowerShell runner"
	@echo "  make test             - Run both backend and firmware tests"
	@echo "  make test-backend     - Run pytest suite (135 tests)"
	@echo "  make test-firmware    - Run native PlatformIO firmware tests (16 tests)"
	@echo "  make benchmarks       - Run empirical safety benchmark suite"
	@echo "  make migrate          - Apply latest Alembic database migrations"
	@echo "  make build-dashboard  - Build production React dashboard bundle"

start:
	powershell -ExecutionPolicy Bypass -File Start-SmartPanel.ps1

test: test-backend test-firmware

test-backend:
	.venv\Scripts\pytest.exe -ra --tb=short -q

test-firmware:
	C:\Users\gunjan\.platformio\penv\Scripts\pio.exe test -d firmware -e native

benchmarks:
	.venv\Scripts\python.exe scripts/run_benchmarks.py

migrate:
	.venv\Scripts\alembic.exe upgrade head

build-dashboard:
	cd dashboard && npm run build

