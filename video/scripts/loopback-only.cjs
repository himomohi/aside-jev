// Remotion의 임시 렌더 서버를 이 프로세스에서만 loopback으로 제한한다.
// Studio·watcher·상주 서비스는 시작하지 않는다.
const net = require('node:net');
const listen = net.Server.prototype.listen;
net.Server.prototype.listen = function (...args) {
  if (typeof args[0] === 'object' && args[0] !== null) {
    if (!('port' in args[0])) throw new Error('TCP 포트가 필요합니다.');
    args[0] = { ...args[0], host: '127.0.0.1', ipv6Only: false };
  } else if (typeof args[0] === 'number') {
    if (typeof args[1] === 'string') args[1] = '127.0.0.1';
    else args.splice(1, 0, '127.0.0.1');
  } else {
    throw new Error('렌더 프로세스에서는 loopback TCP만 허용합니다.');
  }
  return listen.apply(this, args);
};
