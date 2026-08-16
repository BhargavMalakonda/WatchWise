chrome.runtime.onInstalled.addListener(() => {
    chrome.sidePanel.setPanelBehavior({
        openPanelOnActionClick: true
    });
});

chrome.runtime.onMessage.addListener(async (message, sender) => {
    if (message.action !== "openSidePanel") return;

    if (!sender.tab?.windowId) return;

    await chrome.sidePanel.open({
        windowId: sender.tab.windowId
    });
});