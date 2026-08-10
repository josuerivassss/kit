"""Static, hand-maintained ID registry for the enable/disable system.

IDs are intentionally NOT derived at runtime (e.g. by sorting commands
alphabetically) because that would make them shift whenever a command is
renamed or a new one is inserted -- silently corrupting every guild's
`disabled` array. Instead each cog/command gets a permanent, explicit ID
here. To add a new command: append it with the next free number. Never
reuse or renumber an existing ID.

ID shapes:
- Cog:            "c{n}"       e.g. "c3"
- Root command:   "{n}"        e.g. "20"
- Subcommand:     "{n}.{m}"    e.g. "20.1" (m is 1-indexed per parent)
"""
from __future__ import annotations

COG_IDS: dict[str, str] = {
    "Autoroles": "c1",
    "Configuration": "c2",
    "Fun": "c3",
    "Greetings": "c4",
    "Moderation": "c5",
    "Reminders": "c6",
    "Starboard": "c7",
    "Tags": "c8",
    "Tickets": "c9",
    "Utility": "c10",
}

COMMAND_IDS: dict[str, str] = {
    # Autoroles
    "autoroles": "1",
    "autoroles add": "1.1",
    "autoroles list": "1.2",
    "autoroles remove": "1.3",
    # Configuration (both entries are @protected, see cogs/configuration.py)
    "language": "2",
    "prefix": "3",
    # Fun
    "edit": "4",
    "edit communism": "4.1",
    "edit deepfry": "4.2",
    "edit delete": "4.3",
    "edit gay": "4.4",
    "edit gray": "4.5",
    "edit mirror": "4.6",
    "edit pixel": "4.7",
    "edit sonic": "4.8",
    "edit titan": "4.9",
    "edit twoways": "4.10",
    "emojify": "5",
    "reverse": "6",
    "ship": "7",
    # Greetings
    "leave": "8",
    "leave channel": "8.1",
    "leave disable": "8.2",
    "leave enable": "8.3",
    "leave message": "8.4",
    "leave preview": "8.5",
    "welcome": "9",
    "welcome channel": "9.1",
    "welcome disable": "9.2",
    "welcome enable": "9.3",
    "welcome message": "9.4",
    "welcome preview": "9.5",
    # Moderation
    "ban": "10",
    "clear": "11",
    "kick": "12",
    "lockdown": "13",
    "timeout": "14",
    "unban": "15",
    "unlockdown": "16",
    "untimeout": "17",
    # Reminders
    "reminders": "18",
    "reminders add": "18.1",
    "reminders edit": "18.2",
    "reminders list": "18.3",
    "reminders prune": "18.4",
    "reminders remove": "18.5",
    "reminders timezone": "18.6",
    # Starboard
    "starboard": "19",
    "starboard channel": "19.1",
    "starboard disable": "19.2",
    "starboard emoji": "19.3",
    "starboard enable": "19.4",
    "starboard selfstars": "19.5",
    "starboard threshold": "19.6",
    # Tags
    "tag": "20",
    "tag create": "20.1",
    "tag delete": "20.2",
    "tag list": "20.3",
    "tag prune": "20.4",
    "tag update": "20.5",
    "tag view": "20.6",
    # Tickets
    "close": "21",
    "ticket": "22",
    "ticket channel": "22.1",
    "ticket disable": "22.2",
    "ticket enable": "22.3",
    "ticket message": "22.4",
    "ticket role": "22.5",
    # Utility
    "afk": "23",
    "avatar": "24",
    "calendar": "25",
    "color": "26",
    "emoji": "27",
    "emoji add": "27.1",
    "emoji image": "27.2",
    "emoji info": "27.3",
    "emoji remove": "27.4",
    "httpstatus": "28",
    "image": "29",
    "quote": "30",
    "rate": "31",
    "server": "32",
    "server banner": "32.1",
    "server channel": "32.2",
    "server icon": "32.3",
    "server info": "32.4",
    "server members": "32.5",
    "server role": "32.6",
    "server roles": "32.7",
    "translate": "33",
    "user": "34",
    "user avatar": "34.1",
    "user info": "34.2",
}

ID_TO_COG: dict[str, str] = {v: k for k, v in COG_IDS.items()}
ID_TO_COMMAND: dict[str, str] = {v: k for k, v in COMMAND_IDS.items()}


def root_id(command_id: str) -> str:
    """Returns the root command's ID for a (possibly dotted) subcommand ID."""
    return command_id.split(".", 1)[0]