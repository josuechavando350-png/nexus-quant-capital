"""Alcance del census: cadenas, protocolos, direcciones y umbrales.

Fuentes de las direcciones (verificadas el 24 oct 2026):
- Aave V3: bgd-labs/aave-address-book, src/AaveV3<Red>.sol (POOL, ORACLE, WETH_UNDERLYING).
- Morpho Blue: morpho-org/sdks, packages/morpho-ts/src/addresses.ts (campo `blue`); las demás cadenas del mapa ampliado, del
  paquete publicado @morpho-org/morpho-ts 4.1.0 (25 oct 2026).
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
    public_rpcs: tuple              # candidatos sin llave; la sonda descarta los que no sirven
    aave: tuple = ()
    morpho: str = ""
    builder_market: bool = False    # True solo donde hay subasta de builders (Ethereum L1)
    blockscout: str = ""
    extra_rpcs_env: str = ""
    native_eth: bool = True         # el gas se paga en ETH: sin precio del nativo se puede usar el de ETH
    native_usd: float = None        # precio fijo del gas en USD cuando el nativo es una moneda estable (p. ej. USDT0)


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
            "https://eth.merkle.io",
            "https://rpc.mevblocker.io",
            "https://eth-mainnet.public.blastapi.io",
            "https://ethereum.blockpi.network/v1/rpc/public",
            "https://gateway.tenderly.co/public/mainnet",
            "https://eth.api.onfinality.io/public",
            "https://eth1.lava.build",
            "https://eth-pokt.nodies.app",
            "https://api.zan.top/eth-mainnet",
            "https://endpoints.omniatech.io/v1/eth/mainnet/public",
            "https://ethereum.rpc.subquery.network/public",
            "https://rpc.payload.de",
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
            "https://1rpc.io/base",
            "https://base.meowrpc.com",
            "https://base-mainnet.public.blastapi.io",
            "https://base.blockpi.network/v1/rpc/public",
            "https://gateway.tenderly.co/public/base",
            "https://base.api.onfinality.io/public",
            "https://base.lava.build",
            "https://base-pokt.nodies.app",
            "https://api.zan.top/base-mainnet",
            "https://endpoints.omniatech.io/v1/base/mainnet/public",
            "https://base.rpc.subquery.network/public",
            "https://developer-access-mainnet.base.org",
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
            "https://arbitrum.llamarpc.com",
            "https://arbitrum.meowrpc.com",
            "https://arbitrum-one.public.blastapi.io",
            "https://arbitrum.blockpi.network/v1/rpc/public",
            "https://gateway.tenderly.co/public/arbitrum",
            "https://arbitrum.api.onfinality.io/public",
            "https://arb-pokt.nodies.app",
            "https://api.zan.top/arb-one",
            "https://endpoints.omniatech.io/v1/arbitrum/one/public",
            "https://arbitrum.rpc.subquery.network/public",
        ),
        aave=(
            AaveMarket("aave-v3-arbitrum", "0x794a61358D6845594F94dc1DB02A252b5b4814aD", "0xb56c2F0B653B2e0b10C9b928C8580Ac5Df02C7C7"),
        ),
        morpho="0x6c247b1F6182318877311737BaC0844bAa518F5e",
        blockscout="https://arbitrum.blockscout.com",
        extra_rpcs_env="NQC_CENSUS_RPC_ARBITRUM",
    ),
}

# --- Mapa ampliado: Morpho Blue en otras cadenas -------------------------------------------
# Solo Morpho Blue. Direcciones del registro oficial de Morpho (@morpho-org/morpho-ts 4.1.0, lib/esm/addresses.js:
# campos `blue` y `wNative`; leídas el 25 oct 2026). RPC: el público por omisión de viem 2.57.11 (chains/definitions) más
# proveedores públicos conocidos; la sonda y la comprobación de chain_id descartan los que no responden o no son de esa cadena.
# El prefijo de DefiLlama es la mejor estimación: si no da precio, una deuda en moneda estable se valúa por su símbolo.
# Fila: clave, chain_id, prefijo DefiLlama, gas en ETH, precio fijo del gas (USD), wNative, Morpho Blue, explorador blockscout, RPC.
_ZERO = "0x0000000000000000000000000000000000000000"
_MORPHO_ONLY_CHAINS = (
    ("polygon", 137, "polygon", False, None, "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", "0x1bF0c2541F820E775182832f06c0B7Fc27A25f67", "",
     ("https://polygon.drpc.org", "https://polygon-bor-rpc.publicnode.com", "https://polygon-rpc.com", "https://1rpc.io/matic")),
    ("optimism", 10, "optimism", True, None, "0x4200000000000000000000000000000000000006", "0xce95AfbB8EA029495c66020883F87aaE8864AF92",
     "https://optimism.blockscout.com",
     ("https://mainnet.optimism.io", "https://optimism-rpc.publicnode.com", "https://optimism.drpc.org", "https://1rpc.io/op")),
    ("unichain", 130, "unichain", True, None, "0x4200000000000000000000000000000000000006", "0x8f5ae9CddB9f68de460C77730b018Ae7E04a140A",
     "https://unichain.blockscout.com", ("https://mainnet.unichain.org", "https://unichain-rpc.publicnode.com", "https://unichain.drpc.org")),
    ("katana", 747474, "katana", True, None, "0xEE7D8BCFb72bC1880D0Cf19822eB0A2e6577aB62", "0xD50F2DffFd62f94Ee4AEd9ca05C61d0753268aBc", "",
     ("https://rpc.katana.network", "https://katana.drpc.org")),
    ("hyperevm", 999, "hyperliquid", False, None, "0x5555555555555555555555555555555555555555", "0x68e37dE8d93d3496ae143F2E900490f6280C57cD", "",
     ("https://rpc.hyperliquid.xyz/evm", "https://hyperliquid.drpc.org", "https://rpc.hypurrscan.io")),
    ("worldchain", 480, "wc", True, None, "0x4200000000000000000000000000000000000006", "0xE741BC7c34758b4caE05062794E8Ae24978AF432",
     "https://worldchain-mainnet.explorer.alchemy.com",
     ("https://worldchain-mainnet.g.alchemy.com/public", "https://worldchain.drpc.org", "https://480.rpc.thirdweb.com")),
    ("sonic", 146, "sonic", False, None, "0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38", "0xd6c916eB7542D0Ad3f18AEd0FCBD50C582cfa95f", "",
     ("https://rpc.soniclabs.com", "https://sonic-rpc.publicnode.com", "https://sonic.drpc.org")),
    ("bsc", 56, "bsc", False, None, "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "0x01b0Bd309AA75547f7a37Ad7B1219A898E67a83a", "",
     ("https://bsc-rpc.publicnode.com", "https://bsc.drpc.org", "https://bsc-dataseed.bnbchain.org", "https://56.rpc.thirdweb.com")),
    ("linea", 59144, "linea", True, None, "0xe5D7C2a44FfDDf6b295A15c148167daaAf5Cf34f", "0x6B0D716aC0A45536172308e08fC2C40387262c9F", "",
     ("https://rpc.linea.build", "https://linea-rpc.publicnode.com", "https://linea.drpc.org")),
    ("scroll", 534352, "scroll", True, None, "0x5300000000000000000000000000000000000004", "0x2d012EdbAdc37eDc2BC62791B666f9193FDF5a55", "",
     ("https://rpc.scroll.io", "https://scroll-rpc.publicnode.com", "https://scroll.drpc.org")),
    ("sei", 1329, "sei", False, None, "0xE30feDd158A2e3b13e9badaeABaFc5516e95e8C7", "0xc9cDAc20FCeAAF616f7EB0bb6Cd2c69dcfa9094c", "",
     ("https://evm-rpc.sei-apis.com", "https://sei-evm-rpc.publicnode.com")),
    ("monad", 143, "monad", False, None, "0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A", "0xD5D960E8C380B724a48AC59E2DfF1b2CB4a1eAee", "",
     ("https://rpc.monad.xyz", "https://rpc1.monad.xyz", "https://monad-mainnet.drpc.org")),
    ("celo", 42220, "celo", False, None, _ZERO, "0xd24ECdD8C1e0E57a4E26B1a7bbeAa3e95466A569", "https://celo.blockscout.com",
     ("https://forno.celo.org", "https://celo-rpc.publicnode.com", "https://celo.drpc.org")),
    ("etherlink", 42793, "etherlink", False, None, "0xc9B53AB2679f573e480d01e0f49e2B5CFB7a3EAb", "0xbCE7364E63C3B13C73E9977a83c9704E2aCa876e",
     "https://explorer.etherlink.com", ("https://node.mainnet.etherlink.com",)),
    ("hemi", 43111, "hemi", True, None, "0x4200000000000000000000000000000000000006", "0xa4Ca2c2e25b97DA19879201bA49422bc6f181f42",
     "https://explorer.hemi.xyz", ("https://rpc.hemi.network/rpc",)),
    ("ink", 57073, "ink", True, None, "0x4200000000000000000000000000000000000006", "0x857f3EefE8cbda3Bc49367C996cd664A880d3042",
     "https://explorer.inkonchain.com", ("https://rpc-gel.inkonchain.com", "https://rpc-qnd.inkonchain.com", "https://ink.drpc.org")),
    ("lisk", 1135, "lisk", True, None, "0x4200000000000000000000000000000000000006", "0x00cD58DEEbd7A2F1C55dAec715faF8aed5b27BF8",
     "https://blockscout.lisk.com", ("https://rpc.api.lisk.com", "https://lisk.drpc.org")),
    ("soneium", 1868, "soneium", True, None, "0x4200000000000000000000000000000000000006", "0xE75Fc5eA6e74B824954349Ca351eb4e671ADA53a",
     "https://soneium.blockscout.com", ("https://rpc.soneium.org", "https://soneium.drpc.org")),
    ("fraxtal", 252, "fraxtal", False, None, "0xFC00000000000000000000000000000000000006", "0xa6030627d724bA78a59aCf43Be7550b4C5a0653b", "",
     ("https://rpc.frax.com", "https://fraxtal.drpc.org")),
    ("mode", 34443, "mode", True, None, "0x4200000000000000000000000000000000000006", "0xd85cE6BD68487E0AaFb0858FDE1Cd18c76840564",
     "https://explorer.mode.network", ("https://mainnet.mode.network", "https://mode.drpc.org")),
    ("plume", 98866, "plume_mainnet", False, None, "0xEa237441c92CAe6FC17Caaf9a7acB3f953be4bd1", "0x42b18785CE0Aed7BF7Ca43a39471ED4C0A3e0bB5",
     "https://explorer.plume.org", ("https://rpc.plume.org",)),
    ("corn", 21000000, "corn", False, None, "0xda5dDd7270381A7C2717aD10D1c0ecB19e3CDFb2", "0xc2B1E031540e3F3271C5F3819F0cC7479a8DdD90", "",
     ("https://21000000.rpc.thirdweb.com", "https://mainnet.corn-rpc.com")),
    ("tac", 239, "tac", False, None, "0xB63B9f0eb4A6E6f191529D71d4D88cc8900Df2C9", "0x918B9F2E4B44E20c6423105BB6cCEB71473aD35c",
     "https://tac.blockscout.com", ("https://rpc.ankr.com/tac", "https://rpc.tac.build")),
    ("flare", 14, "flare", False, None, "0x1D80c49BbBCd1C0911346656B529DF9E5c2F783d", "0xF4346F5132e810f80a28487a79c7559d9797E8B0",
     "https://flare-explorer.flare.network", ("https://flare-api.flare.network/ext/C/rpc", "https://flare.drpc.org")),
    ("cronos", 25, "cronos", False, None, "0x5C7F8A570d578ED84E63fdFA7b1eE72dEae1AE23", "0xDF9a1DC07e5dEe5ccCCaBeC35e446C70fAF7434e", "",
     ("https://evm.cronos.org", "https://cronos-evm-rpc.publicnode.com", "https://cronos.drpc.org")),
    ("xdc", 50, "xdc", False, None, "0x951857744785E80e2De051c32EE7b25f9c458C42", "0xEa49B0fE898aF913A3826F9f462eE2cDcb854fD9", "",
     ("https://rpc.xdcrpc.com", "https://erpc.xinfin.network")),
    ("kaia", 8217, "klaytn", False, None, "0x19Aac5f612f524B754CA7e7c41cbFa2E981A4432", "0xA8BEebdca34d83C697c302A0594f3c41f3994cd2", "",
     ("https://public-en.node.kaia.io", "https://kaia.drpc.org")),
    ("zerog", 16661, "0g", False, None, "0x1Cd0690fF9a693f5EF2dD976660a8dAFc81A109c", "0x9CDD13a2212D94C4f12190cA30783B743E83C89e", "",
     ("https://evmrpc.0g.ai",)),
    ("abstract", 2741, "abstract", True, None, "0x3439153EB7AF838Ad19d56E1571FBD09333C2809", "0xc85CE8ffdA27b646D269516B8d0Fa6ec2E958B55", "",
     ("https://api.mainnet.abs.xyz",)),
    ("morph", 2818, "morph", True, None, "0x5300000000000000000000000000000000000011", "0xAd10d07901Dc3195c3cb5e78E061F4EA8D9B4905",
     "https://explorer.morphl2.io", ("https://rpc.morphl2.io",)),
    ("megaeth", 4326, "megaeth", True, None, "0x4200000000000000000000000000000000000006", "0x18120312A7cf44DcfEc6dCe5632a431579ED9100", "",
     ("https://mainnet.megaeth.com/rpc",)),
    ("robinhood", 4663, "robinhood", True, None, "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73", "0x9D53d5E3bd5E8d4Cbfa6DB1ca238AEA02E651010",
     "https://robinhoodchain.blockscout.com", ("https://rpc.mainnet.chain.robinhood.com", "https://rpc.ordofi.network")),
    ("stable", 988, "stable", False, 1.0, _ZERO, "0xa40103088A899514E3fe474cD3cc5bf811b1102e", "", ("https://rpc.stable.xyz",)),
    ("tempo", 4217, "tempo", False, 1.0, _ZERO, "0x10EE9AAC980A180dd4DcFc96C746d60B0EA88f97", "", ("https://rpc.tempo.xyz",)),
    ("arc", 5042, "arc", False, 1.0, _ZERO, "0x34CD04070dD72b14E241112F6d83812Df5Af7fCD", "",
     ("https://rpc.mainnet.arc.io", "https://rpc.blockdaemon.mainnet.arc.io")),
    ("bitlayer", 200901, "bitlayer", False, None, "0xfF204e2681A6fA0e2C3FaDe68a1B28fb90E4Fc5F", "0xAeA7eFF1bD3c875c18ef50F0387892dF181431C6", "",
     ("https://rpc.bitlayer.org",)),
    ("gensyn", 685689, "gensyn", True, None, "0x4200000000000000000000000000000000000006", "0x8c45B34999883FF4B47cD3be095D585682cd9227", "",
     ("https://gensyn-mainnet.g.alchemy.com/public",)),
    ("eden", 714, "eden", False, None, "0x00000000000000000000000000000000ce1E571a", "0xF050a2BB0468FF23cF2964AC182196C94D6815C3",
     "https://eden.blockscout.com", ("https://rpc.eden.gateway.fm",)),
)
for _key, _cid, _llama, _eth, _fixed, _wn, _blue, _bs, _rpcs in _MORPHO_ONLY_CHAINS:
    CHAINS[_key] = Chain(key=_key, chain_id=_cid, llama=_llama, weth=_wn, public_rpcs=_rpcs, morpho=_blue, blockscout=_bs,
                         extra_rpcs_env=f"NQC_CENSUS_RPC_{_key.upper()}", native_eth=_eth, native_usd=_fixed)
MORPHO_ONLY_CHAINS = tuple(k for k, *_ in _MORPHO_ONLY_CHAINS)

# Deudas en estas monedas se valúan a 1 USD si DefiLlama no tiene su precio en esa cadena (se marca la fuente).
USD_STABLE_SYMBOLS = frozenset({"USDC", "USDT", "USDT0", "USD₮0", "DAI", "USDS", "USDE", "AUSD", "USDC.E", "USDBC", "PYUSD", "USD1",
                                "RLUSD", "FRXUSD", "FRAX", "GHO", "LUSD", "USDG", "USDH", "USDHL", "USDTB", "FDUSD", "USDX", "MUSD"})


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

# Contratos de entrada compartidos (subastas de orden) conocidos. Además de estos, el
# análisis trata como compartida toda entrada que usan dos o más contratos liquidadores.
# - Arbitrum 0x8ad1…86c1 y Base 0x583d…9b77: `metacall` de la subasta OEV. Verificado a mano con
#   evidencia cruda: tx 0x7aca33d6…753e (Arbitrum) pagó 1.16 ETH y el ganador se quedó $6.41 de un
#   bono de $3,117; tx 0x7360c374…1e1c (Base, 15 liquidaciones Morpho) pagó 3.048 ETH de un bono de
#   $7,357 y perdió $87.81. En ambas cadenas el ETH termina en 0x52b9…c506.
KNOWN_SHARED_ENTRIES = frozenset({
    ("arbitrum", "0x8ad1ae9d97c79aa68a0a151e83ff3942f68f86c1"),
    ("base", "0x583dcfef0d240dc80753f0f0b26513fee27d9b77"),
})

# Cuentas sin código que son parte de un protocolo (no billeteras de un bot). Verificado a mano:
# el bolsillo del LitePSM-USDC de Maker recibe y paga USDC en los swaps DAI↔USDC
# (tx 0x7fc99655…a5cd y 0x5453e660…959b en Ethereum).
CODELESS_PROTOCOL_ACCOUNTS = frozenset({
    "0x37305b1cd40574e4c5ce33f8e8306be057fd7341",
})

# --- Shadow Base/Morpho ------------------------------------------------------------------
# Mercados vigilados y valores de referencia, sacados de la corrida de 30 días del census
# (run 40141321042, 24 sep 20:00 – 24 oct 20:00 UTC, Base/Morpho): mercados con préstamo en USDC
# y (>= 5 liquidaciones o >= $40 de bono directo). Los valores de referencia son del pasado:
#   n          liquidaciones en 30 días        n_dir      las que NO pagaron subasta ("directas")
#   dir_bonus  bono de las directas, USD       kept_dir   parte del bono directo que el ganador se quedó
#   auc_n / auc_bonus  parte de las liquidaciones / del bono que fue por subasta
# El Shadow los usa solo como supuesto declarado; lo que mide en vivo no depende de ellos.
SHADOW_PRIORS_SOURCE = "census run 40141321042 (24 sep–24 oct 2026), Base/Morpho, 30 días"
SHADOW_BASE_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
SHADOW_PRIOR_KEPT_ALL = 0.678       # neto/bono ponderado de las 830 liquidaciones directas con bono >= $1
SHADOW_PRIOR_KEPT_MEDIAN = 0.80     # mediana por liquidación
SHADOW_PRIOR_GAS_USD = 0.31         # gas mediano de una liquidación directa en Base (p90: $2.83)
SHADOW_BASE_MARKETS = [
    {"id": "0xd4a903dc6d949519060c7707f9604fdc9772c046e05c2e3a8fce0bd7196e4109", "label": "cbXRP/USDC lltv 62.5%",
     "n": 778, "n_dir": 450, "dir_bonus": 59560, "kept_dir": 0.584, "auc_n": 0.36, "auc_bonus": 0.8},
    {"id": "0x8793cf302b8ffd655ab97bd1c695dbd967807e8367a65cb2f4edaf1380ba1bda", "label": "WETH/USDC lltv 86.0%",
     "n": 538, "n_dir": 257, "dir_bonus": 3613, "kept_dir": 0.943, "auc_n": 0.46, "auc_bonus": 0.96},
    {"id": "0x0ca10126f6c94cbd9cf0a48cc9516ae5e3dec5aa68303e6d988ee37c5149bf0d", "label": "cbETH/USDC lltv 77.0%",
     "n": 471, "n_dir": 392, "dir_bonus": 29272, "kept_dir": 0.876, "auc_n": 0.11, "auc_bonus": 0.02},
    {"id": "0x09276541cfecb6920a80679a1deced4dde3ae64bf5fc2c9c1f9c21e0c152e1a5", "label": "JitoSOL/USDC lltv 62.5%",
     "n": 217, "n_dir": 58, "dir_bonus": 129, "kept_dir": 0.53, "auc_n": 0.7, "auc_bonus": 0.99},
    {"id": "0x7dc02ff6c536b1d49d7fba770438d79f5bd1f1c78884629b7d1aaee19675782b", "label": "SOL/USDC lltv 62.5%",
     "n": 197, "n_dir": 42, "dir_bonus": 127, "kept_dir": 0.886, "auc_n": 0.76, "auc_bonus": 1.0},
    {"id": "0x73527ddd796e6d4f48387adaae36f6f3d49d606d7f2a15eb0c931416a58875d8", "label": "cbDOGE/USDC lltv 62.5%",
     "n": 135, "n_dir": 24, "dir_bonus": 13, "kept_dir": 0.184, "auc_n": 0.77, "auc_bonus": 1.0},
    {"id": "0xd7520ad198b497b6eb75bc690268f4597630dbc12e305e9d4105843bab36e41d", "label": "cbADA/USDC lltv 62.5%",
     "n": 85, "n_dir": 10, "dir_bonus": 15, "kept_dir": 0.031, "auc_n": 0.88, "auc_bonus": 1.0},
    {"id": "0x9125d0fa03c3137166df68bcc72283477830de2a4a5536512374c573ad4583c3", "label": "cbLTC/USDC lltv 62.5%",
     "n": 84, "n_dir": 21, "dir_bonus": 71, "kept_dir": 0.673, "auc_n": 0.74, "auc_bonus": 1.0},
    {"id": "0xe458a501c1103ca3b256f2bcb45d223263fb34b6349d82675494ce3a94ce1327", "label": "cbZEC/USDC lltv 62.5%",
     "n": 61, "n_dir": 19, "dir_bonus": 5933, "kept_dir": 0.47, "auc_n": 0.65, "auc_bonus": 0.35},
    {"id": "0x34f676bd8db106d6cdc90d0fb44145cea2f393310a794812cb1c5a8726b60913", "label": "wbCOIN/USDC lltv 86.0%",
     "n": 28, "n_dir": 28, "dir_bonus": 7, "kept_dir": 0.757, "auc_n": 0.0, "auc_bonus": 0.0},
    {"id": "0x9103c3b4e834476c9a62ea009ba2c884ee42e94e6e314a26f04d312434191836", "label": "cbBTC/USDC lltv 86.0%",
     "n": 12, "n_dir": 4, "dir_bonus": 1, "kept_dir": None, "auc_n": 0.64, "auc_bonus": 1.0},
    {"id": "0xdaa04f6819210b11fe4e3b65300c725c32e55755e3598671559b9ae3bac453d7", "label": "AERO/USDC lltv 62.5%",
     "n": 9, "n_dir": 7, "dir_bonus": 50, "kept_dir": 0.713, "auc_n": 0.22, "auc_bonus": 0.05},
    {"id": "0x76629002c9fdb20fb2092053a4f22c5c65e04a81887218b9546f2a2d82b4c0a8", "label": "cbHYPE/USDC lltv 62.5%",
     "n": 8, "n_dir": 0, "dir_bonus": 0, "kept_dir": None, "auc_n": 1.0, "auc_bonus": 1.0},
    {"id": "0x45f3b5688e7ba25071f78d1ce51d1b893faa3c86897b12204cdff3af6b3611f8", "label": "mBASIS/USDC lltv 86.0%",
     "n": 7, "n_dir": 5, "dir_bonus": 12, "kept_dir": 0.78, "auc_n": 0.29, "auc_bonus": 0.34},
    {"id": "0x1c21c59df9db44bf6f645d854ee710a8ca17b479451447e9f56758aee10a2fad", "label": "cbETH/USDC lltv 86.0%",
     "n": 5, "n_dir": 1, "dir_bonus": 44, "kept_dir": 0.971, "auc_n": 0.75, "auc_bonus": 0.05},
    {"id": "0xb3920b96dec75b6a1144b71f963f30236fb200f3e33e93c2e9c0d222c1fa53c2", "label": "stkWELL/USDC lltv 62.5%",
     "n": 5, "n_dir": 5, "dir_bonus": 102, "kept_dir": 0.704, "auc_n": 0.0, "auc_bonus": 0.0},
    {"id": "0x1a3e69d0109bb1be42b80e11034bb6ee98fc466721f26845dc83b2aa8d979137", "label": "yoUSD/USDC lltv 91.5%",
     "n": 3, "n_dir": 1, "dir_bonus": 191, "kept_dir": 1.0, "auc_n": 0.67, "auc_bonus": 0.05},
    {"id": "0xdba352d93a64b17c71104cbddc6aef85cd432322a1446b5b65163cbbc615cd0c", "label": "cbETH/USDC lltv 86.0%",
     "n": 2, "n_dir": 1, "dir_bonus": 198, "kept_dir": 0.952, "auc_n": 0.5, "auc_bonus": 0.01},
    {"id": "0x3b82e29f0890186d7a66059699e522930c4cbe78ffbccb468c577daa5bc4bc10", "label": "cbZEC/USDC lltv 77.0%",
     "n": 1, "n_dir": 1, "dir_bonus": 257, "kept_dir": 0.235, "auc_n": 0.0, "auc_bonus": 0.0},
]

# Ventana extra antes del inicio para encontrar la última actualización de
# oráculo de las primeras liquidaciones (heartbeats de hasta 24 h).
ORACLE_LOOKBACK_SECONDS = 26 * 3600
