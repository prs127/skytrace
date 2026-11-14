import asyncio, sys, re
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1400, "height": 900}); errs = []
        pg.on("pageerror", lambda e: errs.append("PAGE " + str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text[:150]))
        await pg.goto(sys.argv[1]); await pg.wait_for_timeout(4000)
        print("badge:", await pg.inner_text("#modeBadge"), "| live link visible:", await pg.is_visible("#liveLink"))
        await pg.fill("#coordInput", "10h03m07.63s +03d21m00.8s"); await pg.click("#goBtn"); await pg.wait_for_timeout(800)
        print("msg:", await pg.inner_text("#coordMsg"), "| href:", await pg.evaluate("(document.querySelector('#coordMsg a')||{}).href"))
        print("share:", await pg.input_value("#shareUrl"))
        html = await pg.content(); print("AI mentions in page:", re.findall(r"(?i)claude|anthropic|\bAI\b|AI-assist", html))
        print("errors:", errs); await b.close()
asyncio.run(main())
