from aiosteamist import SteamistStatus

assert SteamistStatus(temp=75, temp_units="F", minute_remain=0, active=True).temp == 75
