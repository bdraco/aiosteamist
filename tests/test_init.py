from aiosteamist import SteamistStatus

assert SteamistStatus(temp=75, temp_units="F", minutes_remain=0, active=True).temp == 75
