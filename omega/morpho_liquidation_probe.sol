// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

interface OmegaToken {
    function balanceOf(address) external view returns (uint256);
    function allowance(address,address) external view returns (uint256);
    function approve(address,uint256) external returns (bool);
    function transfer(address,uint256) external returns (bool);
}
interface OmegaMorpho {
    function flashLoan(address,uint256,bytes calldata) external;
}
interface OmegaAave {
    function liquidationCall(address,address,address,uint256,bool) external;
}

/// @notice Research-only same-asset liquidation probe for a local historical fork.
/// @dev No live deployment authorization, gas sponsorship or all-in-profit claim.
/// The Aave hash authenticates the proxy bytes only, not its implementation.
contract OmegaMorphoLiquidationProbe {
    error Unauthorized();
    error InvalidDependencies();
    error CodeIdentity();
    error InvalidPlan();
    error AnchorMismatch();
    error Busy();
    error Consumed();
    error Prefunded();
    error ExistingAllowance();
    error Liquidity();
    error CallbackAuth();
    error CallbackPlan();
    error FreshPrincipal();
    error CallbackMissing();
    error InsufficientSurplus();
    error RepaymentMismatch();
    error TokenCall();

    struct Plan {
        uint256 chainId;
        uint256 blockNumber;
        uint256 timestamp;
        bytes32 parentHash;
        address borrower;
        uint256 principal;
        uint256 minimumSurplus;
        bytes32 executionId;
    }

    address public immutable operator;
    address public immutable lender;
    address public immutable pool;
    address public immutable asset;
    bytes32 public immutable lenderCodeHash;
    bytes32 public immutable poolProxyCodeHash;
    bytes32 public immutable assetCodeHash;
    // 0 idle, 1 requested, 2 callback active/completed, 3 settlement.
    uint256 public phase;
    bytes32 public activePlanHash;
    uint256 private activePrincipal;
    uint256 public callbackCount;
    mapping(bytes32 => bool) public consumed;

    event ResearchLiquidation(bytes32 indexed executionId,bytes32 indexed planHash,
        uint256 principal,uint256 proceedsBeforeRepayment,uint256 surplus);

    constructor(address operator_,address lender_,address pool_,address asset_,
                bytes32 lenderHash_,bytes32 poolHash_,bytes32 assetHash_) {
        if (operator_==address(0) || lender_==address(0) || pool_==address(0) || asset_==address(0)
            || lender_==pool_ || lender_==asset_ || pool_==asset_
            || operator_==lender_ || operator_==pool_ || operator_==asset_)
            revert InvalidDependencies();
        operator=operator_;lender=lender_;pool=pool_;asset=asset_;
        lenderCodeHash=lenderHash_;poolProxyCodeHash=poolHash_;assetCodeHash=assetHash_;
        _codes();
    }

    function _codes() private view {
        if (lender.code.length==0 || pool.code.length==0 || asset.code.length==0
            || lender.codehash!=lenderCodeHash || pool.codehash!=poolProxyCodeHash
            || asset.codehash!=assetCodeHash) revert CodeIdentity();
    }

    function _anchor(Plan memory p) private view {
        if (block.chainid!=p.chainId || block.number!=p.blockNumber
            || block.timestamp!=p.timestamp || block.number==0
            || p.parentHash==bytes32(0) || blockhash(block.number-1)!=p.parentHash)
            revert AnchorMismatch();
    }

    function execute(Plan calldata p) external returns (uint256 surplus) {
        if (msg.sender!=operator) revert Unauthorized();
        if (phase!=0) revert Busy();
        if (p.borrower==address(0) || p.principal==0 || p.minimumSurplus==0
            || p.executionId==bytes32(0)) revert InvalidPlan();
        if (consumed[p.executionId]) revert Consumed();
        _codes();_anchor(p);
        OmegaToken token=OmegaToken(asset);
        if (token.balanceOf(address(this))!=0 || address(this).balance!=0) revert Prefunded();
        if (token.allowance(address(this),lender)!=0 || token.allowance(address(this),pool)!=0)
            revert ExistingAllowance();
        uint256 lenderBefore=token.balanceOf(lender);
        if (lenderBefore<p.principal) revert Liquidity();
        bytes memory data=abi.encode(p);
        activePlanHash=keccak256(data);activePrincipal=p.principal;callbackCount=0;phase=1;
        OmegaMorpho(lender).flashLoan(asset,p.principal,data);
        if (phase!=2 || callbackCount!=1) revert CallbackMissing();
        if (token.allowance(address(this),lender)!=0 || token.allowance(address(this),pool)!=0
            || token.balanceOf(lender)!=lenderBefore) revert RepaymentMismatch();
        surplus=token.balanceOf(address(this));
        if (surplus<p.minimumSurplus) revert InsufficientSurplus();
        phase=3;consumed[p.executionId]=true;
        _tokenCall(abi.encodeWithSelector(OmegaToken.transfer.selector,operator,surplus));
        if (token.balanceOf(address(this))!=0) revert RepaymentMismatch();
        emit ResearchLiquidation(p.executionId,activePlanHash,p.principal,p.principal+surplus,surplus);
        activePlanHash=bytes32(0);activePrincipal=0;phase=0;
    }

    function onMorphoFlashLoan(uint256 amount,bytes calldata data) external {
        if (msg.sender!=lender || phase!=1) revert CallbackAuth();
        if (amount!=activePrincipal || keccak256(data)!=activePlanHash) revert CallbackPlan();
        Plan memory p=abi.decode(data,(Plan));
        _codes();_anchor(p);
        OmegaToken token=OmegaToken(asset);
        if (token.balanceOf(address(this))!=amount) revert FreshPrincipal();
        phase=2;callbackCount++;
        _tokenCall(abi.encodeWithSelector(OmegaToken.approve.selector,pool,amount));
        OmegaAave(pool).liquidationCall(asset,asset,p.borrower,amount,false);
        _tokenCall(abi.encodeWithSelector(OmegaToken.approve.selector,pool,0));
        uint256 balance=token.balanceOf(address(this));
        if (balance<amount || balance-amount<p.minimumSurplus) revert InsufficientSurplus();
        _tokenCall(abi.encodeWithSelector(OmegaToken.approve.selector,lender,amount));
    }

    function _tokenCall(bytes memory data) private {
        (bool ok,bytes memory result)=asset.call(data);
        if (!ok || (result.length!=0 && (result.length!=32 || !abi.decode(result,(bool)))))
            revert TokenCall();
    }
}
