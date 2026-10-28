"""Small diagnostic/automation MCP client. Never prints image payloads or headers."""
import json
import urllib.request
from urllib.parse import urlparse

class Client:
    def __init__(self, url='http://localhost:3000/bb-mcp', timeout=20, max_bytes=64*1024*1024):
        parsed = urlparse(url)
        if parsed.scheme != 'http' or parsed.hostname not in ('localhost','127.0.0.1','::1') or parsed.username or parsed.password:
            raise ValueError('Helper supports unauthenticated loopback HTTP only; use connected tools for remote/authenticated MCP')
        self.url,self.timeout,self.max_bytes = url,timeout,max_bytes
        self.session = None; self.protocol = None; self.seq = 0
        self.info = self.call('initialize', {'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'minecraft-modeling-item','version':'1.0.0'}})
        self.protocol = self.info.get('protocolVersion')
        self.notify('notifications/initialized', {})

    @staticmethod
    def decode(raw, content_type, expected):
        text = raw.decode('utf-8')
        if 'text/event-stream' in content_type:
            messages=[]
            for block in text.replace('\r\n','\n').split('\n\n'):
                data='\n'.join(line[5:].lstrip(' ') for line in block.splitlines() if line.startswith('data:'))
                if data:
                    messages.append(json.loads(data))
            message=next((m for m in messages if m.get('id') == expected),None)
            if message is None: raise ValueError('SSE response has no matching JSON-RPC result')
        else:
            message=json.loads(text)
        if message.get('id') != expected: raise ValueError('Mismatched JSON-RPC response ID')
        if 'error' in message: raise RuntimeError('MCP error: '+str(message['error']))
        return message['result']

    def request(self, payload, notification=False):
        headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
        if self.session: headers['Mcp-Session-Id']=self.session
        if self.protocol: headers['MCP-Protocol-Version']=self.protocol
        req=urllib.request.Request(self.url, json.dumps(payload).encode(), headers, method='POST')
        with urllib.request.urlopen(req,timeout=self.timeout) as response:
            if response.headers.get('Mcp-Session-Id'): self.session=response.headers['Mcp-Session-Id']
            if notification: return None
            raw=response.read(self.max_bytes+1)
            if len(raw)>self.max_bytes: raise ValueError('Response exceeds helper limit; use smaller scope')
            return self.decode(raw,response.headers.get('Content-Type',''),payload['id'])

    def call(self, method, params):
        self.seq+=1
        return self.request({'jsonrpc':'2.0','id':self.seq,'method':method,'params':params})

    def notify(self, method, params):
        self.request({'jsonrpc':'2.0','method':method,'params':params},True)

    def tool(self, name, arguments):
        result=self.call('tools/call',{'name':name,'arguments':arguments})
        if result.get('isError'): raise RuntimeError('Tool failed: '+str(result.get('content',[]))[:1200])
        return result

    def close(self):
        if self.session:
            headers={'Mcp-Session-Id':self.session}
            if self.protocol:headers['MCP-Protocol-Version']=self.protocol
            try:
                with urllib.request.urlopen(urllib.request.Request(self.url,headers=headers,method='DELETE'),timeout=self.timeout):pass
            except Exception:pass
            self.session=None

    def __enter__(self): return self
    def __exit__(self,*args): self.close()

def structured(result):
    if 'structuredContent' in result:return result['structuredContent']
    texts=[c['text'] for c in result.get('content',[]) if c.get('type')=='text']
    for text in texts:
        try:return json.loads(text)
        except json.JSONDecodeError:pass
    raise ValueError('Tool did not return structured JSON')
