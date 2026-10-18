from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    firecrawl_api_url: str = "http://localhost:3002"
    firecrawl_api_key: str = ""

    max_concurrency: int = 2
    request_delay_seconds: float = 1.5
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 job-aggregator-student-project"
    )

    # Kept as plain strings: pydantic-settings wants JSON for list env vars, commas are friendlier.
    search_queries: str = "intern,new grad,entry level"
    locations: str = "India"

    # Greenhouse board tokens (the name in boards-api.greenhouse.io/v1/boards/<token>/jobs).
    greenhouse_companies: str = (
        "databricks,okta,gitlab,rubrik,netskope,elastic,twilio,coinbase,datadog,groww,"
        "airbnb,stripe,mixpanel,anthropic,zscaler,vercel,mongodb,figma,cloudflare"
    )

    # LLM extraction (Ollama). Small defaults: a 3B model is what fits a 4 GB GPU.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout_seconds: float = 180
    ollama_num_ctx: int = 6144
    extraction_max_chars: int = 12000
    extraction_min_chars: int = 300  # shorter texts (e.g. listing cards) have nothing to extract

    output_dir: Path = Path("data")
    max_markdown_chars: int = 20000

    @property
    def query_list(self) -> list[str]:
        return _split(self.search_queries)

    @property
    def greenhouse_company_list(self) -> list[str]:
        return _split(self.greenhouse_companies)

    @property
    def location_list(self) -> list[str]:
        return _split(self.locations)
