"""Alcance del census: cadenas, protocolos, direcciones y umbrales.

Fuentes de las direcciones (verificadas el 24 oct 2026):
- Aave V3: bgd-labs/aave-address-book, src/AaveV3<Red>.sol (POOL, ORACLE, WETH_UNDERLYING).
- Morpho Blue: morpho-org/sdks, packages/morpho-ts/src/addresses.ts (campo `blue`).
- Eventos: aave-address-book IPool.LiquidationCall y morpho-blue src/libraries/EventsLib.sol.
"""

from dataclasses import dataclass

from .keccak import selector

# --- Eventos -----------------------------------------------------------------
AAVE_LIQUIDATION_TOPIC = "0xe413a321e8681d831f4dbccbca790d2952b56f977908e45be37335533e005286"
MORPHO_LIQUIDATE_TOPIC = "0xa4946ede45d0c6f06a0f5ce92c9ad3b4751452d2fe0e25010783bcab57a67e41"
ANSWER_UPDATED_TOPIC = "0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f"
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# --- Selectores ----------------------------------------------------------------
SEL = {
    "decimals": "0x313ce567",
    "symbol": "0x95d89b41",
    "getAssetPrice": "0xb3596f07",
    "getSourceOfAsset": "0x92bf2be0",
    "BASE_CURRENCY_UNIT": "0x8c89b64f",
    "aggregator": "0x245a7bfc",
    "ASSET_TO_USD_AGGREGATOR": "0x4ebdc284",
    "BASE_TO_USD_AGGREGATOR": "0xd221087c",
    "REFERENCE_FEED": selector("REFERENCE_FEED()"),
    "BASE_FEED_1": "0xf50a4718",
    "BASE_FEED_2": "0xdc53858c",
    "QUOTE_FEED_1": "0x56095e11",
    "QUOTE_FEED_2": "0xacfbd39e",
    "idToMarketParams": "0x2c3c9157",
}

# Firmas, para que las pruebas comprueben las constantes de arriba.
SIGNATURES = {
    AAVE_LIQUIDATION_TOPIC: "LiquidationCall(address,address,address,uint256,uint256,address,bool)",
    MORPHO_LIQUIDATE_TOPIC: "Liquidate(bytes32,address,address,uint256,uint256,uint256,uint256,uint256)",
    ANSWER_UPDATED_TOPIC: "AnswerUpdated(int256,uint256,uint256)",
    ERC20_TRANSFER_TOPIC: "Transfer(address,address,uint256)",
}
SELECTOR_SIGNATURES = {
    "decimals": "decimals()",
    "symbol": "symbol()",
    "getAssetPrice": "getAssetPrice(address)",
    "getSourceOfAsset": "getSourceOfAsset(address)",
    "BASE_CURRENCY_UNIT": "BASE_CURRENCY_UNIT()",
    "aggregator": "aggregator()",
    "ASSET_TO_USD_AGGREGATOR": "ASSET_TO_USD_AGGREGATOR()",
    "BASE_TO_USD_AGGREGATOR": "BASE_TO_USD_AGGREGATOR()",
    "REFERENCE_FEED": "REFERENCE_FEED()",
    "BASE_FEED_1": "BASE_FEED_1()",
    "BASE_FEED_2": "BASE_FEED_2()",
    "QUOTE_FEED_1": "QUOTE_FEED_1()",
    "QUOTE_FEED_2": "QUOTE_FEED_2()",
    "idToMarketParams": "idToMarketParams(bytes32)",
}

# Morpho Blue: LIF = min(1.15, 1 / (1 - 0.3 * (1 - lltv)))   (Morpho.sol, ConstantsLib.sol)
MORPHO_LIQUIDATION_CURSOR = 0.3
MORPHO_MAX_LIF = 1.15


@dataclass(frozen=True)
class AaveMarket:
    name: str
    pool: str
    oracle: str


@dataclass(frozen=True)
class Chain:
    key: str
    chain_id: int
    llama: str                      # prefijo de DefiLlama
    weth: str
    public_rpcs: tuple
    aave: tuple = ()
    morpho: str = ""
    builder_market: bool = False    # True solo donde hay subasta de builders (Ethereum L1)
    blockscout: str = ""
    extra_rpcs_env: str = ""


CHAINS = {
    "ethereum": Chain(
        key="ethereum",
        chain_id=1,
        llama="ethereum",
        weth="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        public_rpcs=(
            "https://ethereum-rpc.publicnode.com",
            "https://eth.drpc.org",
            "https://eth.llamarpc.com",
            "https://1rpc.io/eth",
        ),
        aave=(
            AaveMarket("aave-v3-core", "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2", "0x54586bE62E3c3580375aE3723C145253060Ca0C2"),
            AaveMarket("aave-v3-lido", "0x4e033931ad43597d96D6bcc25c280717730B58B1", "0xE3C061981870C0C7b1f3C4F4bB36B95f1F260BE6"),
            AaveMarket("aave-v3-etherfi", "0x0AA97c284e98396202b6A04024F5E2c65026F3c0", "0x43b64f28A678944E0655404B0B98E443851cC34F"),
        ),
        morpho="0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
        builder_market=True,
        blockscout="https://eth.blockscout.com",
        extra_rpcs_env="NQC_CENSUS_RPC_ETHEREUM",
    ),
    "base": Chain(
        key="base",
        chain_id=8453,
        llama="base",
        weth="0x4200000000000000000000000000000000000006",
        public_rpcs=(
            "https://base-rpc.publicnode.com",
            "https://base.drpc.org",
            "https://mainnet.base.org",
            "https://base.llamarpc.com",
        ),
        aave=(
            AaveMarket("aave-v3-base", "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5", "0x2Cc0Fc26eD4563A5ce5e8bdcfe1A2878676Ae156"),
        ),
        morpho="0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
        blockscout="https://base.blockscout.com",
        extra_rpcs_env="NQC_CENSUS_RPC_BASE",
    ),
    "arbitrum": Chain(
        key="arbitrum",
        chain_id=42161,
        llama="arbitrum",
        weth="0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        public_rpcs=(
            "https://arbitrum-one-rpc.publicnode.com",
            "https://arbitrum.drpc.org",
            "https://arb1.arbitrum.io/rpc",
            "https://1rpc.io/arb",
        ),
        aave=(
            AaveMarket("aave-v3-arbitrum", "0x794a61358D6845594F94dc1DB02A252b5b4814aD", "0xb56c2F0B653B2e0b10C9b928C8580Ac5Df02C7C7"),
        ),
        morpho="0x6c247b1F6182318877311737BaC0844bAa518F5e",
        blockscout="https://arbitrum.blockscout.com",
        extra_rpcs_env="NQC_CENSUS_RPC_ARBITRUM",
    ),
}


@dataclass(frozen=True)
class Thresholds:
    """Umbrales iniciales de saturación. Son supuestos de arranque, no calibrados.

    El PDF del Miner (cap. 4) define virgen / disputada / muerta de forma
    cualitativa; estos números la vuelven medible y se ajustarán con los datos.
    """

    min_sample: int = 3
    virgin_max_winners: int = 1
    virgin_max_builder_share: float = 0.20
    virgin_min_blocks: int = 2
    dead_min_winners: int = 4
    dead_min_builder_share: float = 0.80
    dead_same_block_builder_share: float = 0.60


THRESHOLDS = Thresholds()

# Ventana extra antes del inicio para encontrar la última actualización de
# oráculo de las primeras liquidaciones (heartbeats de hasta 24 h).
ORACLE_LOOKBACK_SECONDS = 26 * 3600
