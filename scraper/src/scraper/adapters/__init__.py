from scraper.adapters.base import SourceAdapter
from scraper.adapters.google import GoogleAdapter
from scraper.adapters.greenhouse import GreenhouseAdapter
from scraper.adapters.internshala import InternshalaAdapter
from scraper.adapters.microsoft import MicrosoftAdapter
from scraper.adapters.shine import ShineAdapter
from scraper.adapters.unstop import UnstopAdapter
from scraper.adapters.ycombinator import YCombinatorAdapter

# Adding a new site: write the adapter class, add one line here.
REGISTRY: dict[str, type[SourceAdapter]] = {
    MicrosoftAdapter.name: MicrosoftAdapter,
    InternshalaAdapter.name: InternshalaAdapter,
    GoogleAdapter.name: GoogleAdapter,
    YCombinatorAdapter.name: YCombinatorAdapter,
    GreenhouseAdapter.name: GreenhouseAdapter,
    UnstopAdapter.name: UnstopAdapter,
    ShineAdapter.name: ShineAdapter,
}


def get_adapter(name: str, **kwargs) -> SourceAdapter:
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise ValueError(f"Unknown source {name!r}. Available: {', '.join(sorted(REGISTRY))}")
    return cls(**kwargs)
