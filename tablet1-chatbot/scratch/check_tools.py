import sys
sys.path.append('pluang-bot')
from pluang_mcp import PluangMCPClient
import json

# Let's inspect the tools and their descriptions
t = json.load(open('pluang-bot/tokens.json'))['access_token']
c = PluangMCPClient(t)
# We don't even need network if we check the tool description from previous cached or let's see if we can check the tool cache or description
# Wait, let's check pluang_mcp.py line 1 to 50
