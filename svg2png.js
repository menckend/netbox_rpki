const { chromium } = require('playwright');
(async () => {
    try {
        const browser = await chromium.launch();
        const context = await browser.newContext({ viewport: { width: 500, height: 500 } });
        const page = await context.newPage();
        await page.goto('file:///home/mencken/src/netbox_rpki/images/logo.svg', { waitUntil: 'load' });
        const svg = await page.$('svg');
        await svg.screenshot({ path: '/home/mencken/src/netbox_rpki/images/logo.png', omitBackground: true });
        console.log('Saved to /home/mencken/src/netbox_rpki/images/logo.png');
        await browser.close();
    } catch (e) {
        console.error('Error saving PNG:', e);
        process.exit(1);
    }
})();
