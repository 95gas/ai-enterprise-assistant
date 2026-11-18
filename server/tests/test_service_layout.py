from pathlib import Path


def test_document_and_api_services_are_packages_under_services():
    services_dir = Path(__file__).parents[1] / "src" / "services"
    common_dir = Path(__file__).parents[1] / "src" / "common"
    assert (services_dir / "chat" / "app.py").is_file()
    assert (services_dir / "rag" / "app.py").is_file()
    assert (services_dir / "authentication" / "app.py").is_file()
    assert (services_dir / "md_maker" / "app.py").is_file()
    assert (services_dir / "md_ingestor" / "app.py").is_file()
    assert (services_dir / "temporal" / "worker.py").is_file()
    assert not (services_dir / "manager.py").exists()
    assert not (services_dir / "apps").exists()
    assert not (services_dir / "common").exists()
    assert (common_dir / "microservices" / "base.py").is_file()
    assert (common_dir / "microservices" / "schemas.py").is_file()
    assert (common_dir / "document_processing").is_dir()
