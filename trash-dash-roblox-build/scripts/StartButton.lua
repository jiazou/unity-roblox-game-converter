local TeleportService = game:GetService("TeleportService")

﻿using System.Collections
#if UNITY_ANALYTICS
#endif
#if UNITY_PURCHASING
#endif

local function StartGame()
    {
        if PlayerData.instance.ftueLevel == 0 then
            PlayerData.instance.ftueLevel = 1
            PlayerData.instance.Save()
#if UNITY_ANALYTICS
            AnalyticsEvent.FirstInteraction("start_button_pressed")
#endif
end
#if UNITY_PURCHASING
        local module = StandardPurchasingModule.Instance()
#endif
        -- LoadScene: use TeleportService or place switching("main")
end
end