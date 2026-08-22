ERC20_ABI = [
    {
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

WHYPE_ABI = ERC20_ABI + [
    {
        "inputs": [],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "withdraw",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

VAULT_ABI = [
    {
        "inputs": [{"name": "receiver", "type": "address"}],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "lstAmount", "type": "uint256"},
            {"name": "receiver", "type": "address"},
            {"name": "minHYPEOut", "type": "uint256"},
        ],
        "name": "redeemLST",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getAssociatedLST",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "grossAssets",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

DEX_KERNEL_ABI = [
    {
        "inputs": [
            {"name": "vault", "type": "address"},
            {"name": "lstAmount", "type": "uint256"},
            {"name": "receiver", "type": "address"},
            {"name": "minWhypeOut", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
        ],
        "name": "sellLST",
        "outputs": [
            {"name": "whypeOut", "type": "uint256"},
            {"name": "receipt", "type": "address"},
            {"name": "tokenId", "type": "uint256"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

NATIVE_HYPE_ROUTER_ABI = [
    {
        "type": "receive",
        "stateMutability": "payable",
    },
    {
        "inputs": [
            {"name": "minSharesOut", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
        ],
        "name": "addLiquidityWithHype",
        "outputs": [{"name": "sharesOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "sharesIn", "type": "uint256"},
            {"name": "minHypeOut", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
        ],
        "name": "removeLiquidityToHype",
        "outputs": [{"name": "hypeOut", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "vault", "type": "address"},
            {"name": "lstAmount", "type": "uint256"},
            {"name": "minHypeOut", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
        ],
        "name": "sellLSTForHype",
        "outputs": [
            {"name": "hypeOut", "type": "uint256"},
            {"name": "receipt", "type": "address"},
            {"name": "tokenId", "type": "uint256"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

