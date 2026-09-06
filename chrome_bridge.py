"""Operate a dedicated tab in the user's signed-in Chrome; never read cookies."""
import json
import subprocess
import time

def apple(script,*args):
    result=subprocess.run(['osascript','-e',script,'--',*[str(x) for x in args]],capture_output=True,text=True,timeout=30)
    if result.returncode:raise RuntimeError(result.stderr.strip()[:500])
    return result.stdout.strip()

class ChromeTab:
    def __enter__(self):
        # Check the Chrome setting before opening any tab.
        apple('tell application "Google Chrome" to execute active tab of front window javascript "document.title"')
        value=apple('''tell application "Google Chrome"
set w to front window
set t to make new tab at end of tabs of w with properties {URL:"about:blank"}
return (id of w as text) & "," & (id of t as text)
end tell''')
        self.window,self.tab=map(int,value.split(','));return self
    def evaluate(self,code):
        return apple('''on run argv
 tell application "Google Chrome"
 return execute tab id (item 2 of argv as integer) of window id (item 1 of argv as integer) javascript (item 3 of argv)
 end tell
end run''',self.window,self.tab,code)
    def goto(self,url):
        apple('''on run argv
 tell application "Google Chrome" to set URL of tab id (item 2 of argv as integer) of window id (item 1 of argv as integer) to (item 3 of argv)
end run''',self.window,self.tab,url)
        for _ in range(30):
            time.sleep(1)
            try:
                if self.evaluate('document.readyState')=='complete':break
            except RuntimeError:pass
        time.sleep(2)
    def __exit__(self,*args):
        try:apple('''on run argv
 tell application "Google Chrome" to close tab id (item 2 of argv as integer) of window id (item 1 of argv as integer)
end run''',self.window,self.tab)
        except Exception:pass
