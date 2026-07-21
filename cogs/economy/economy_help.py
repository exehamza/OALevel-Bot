# Permission hierarchy levels matching your main HelpCog
PERM_MEMBER = 0
PERM_MOD = 1
PERM_ADMIN = 2

# Registry for all Economy sub-module commands
ECONOMY_COMMAND_DATA = {
    # --- ECONOMY: GENERAL ---
    "balance": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["bal"],
        "usage": "[@member]",
        "desc": "Shows the current node balance of a member."
    },
    "daily": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Claims daily node reward."
    },
    "monthly": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Claims monthly node reward."
    },
    "richest": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Shows top members by node balance."
    },
    "transactions": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["tx"],
        "usage": "",
        "desc": "Shows personal node transaction history."
    },
    "give": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["transfer", "send"],
        "usage": "<@member> <amount>",
        "desc": "Transfers nodes to another member."
    },

    # --- ECONOMY: ADMIN ---
    "addnodes": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Adds nodes to a member account."
    },
    "removenodes": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Removes nodes from a member account."
    },
    "setnodes": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Sets the node balance for a member."
    },
    "economyreset": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member>",
        "desc": "Resets economy data for a member."
    },
    "economylog": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "[@member|user_id]",
        "desc": "Shows administrative economy transaction logs."
    },

    # --- ECONOMY: GAMES ---
    "coinflip": {
        "category": "Games",
        "level": PERM_MEMBER,
        "aliases": ["cf"],
        "usage": "<bet>",
        "desc": "Flips a coin to double or lose the bet."
    },
    "slots": {
        "category": "Games",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<bet>",
        "desc": "Plays the slot machine with a node bet."
    }
}