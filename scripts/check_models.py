from __future__ import annotations

import sys

from northstar_rag.config import ConfigurationError, Settings
from northstar_rag.nebius import NebiusError, NebiusGateway, validate_configured_models


def main() -> None:
    gateway: NebiusGateway | None = None
    try:
        settings = Settings.from_env()
        gateway = NebiusGateway(settings)
        validate_configured_models(gateway, settings)
    except (ConfigurationError, NebiusError) as error:
        print(f"Model validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    finally:
        if gateway is not None:
            gateway.close()

    print(f"Available: NEBIUS_EMBEDDING_MODEL={settings.embedding_model}")
    print(f"Available: NEBIUS_RERANK_MODEL={settings.rerank_model}")
    print(f"Available: NEBIUS_CHAT_MODEL={settings.chat_model}")


if __name__ == "__main__":
    main()
