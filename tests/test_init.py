from aiosteamist import SteamistStatus


def test_simple():
    assert (
        SteamistStatus(temp=75, temp_units="F", minutes_remain=0, active=True).temp
        == 75
    )
