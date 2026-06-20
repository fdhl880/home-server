const localtunnel = require('localtunnel');

(async () => {
  try {
    const tunnel = await localtunnel({ port: 8080 });
    console.log('your url is:', tunnel.url);

    tunnel.on('close', () => {
      console.log('tunnel closed');
      process.exit(1);
    });

    tunnel.on('error', (err) => {
      console.error('tunnel error:', err);
    });

    // Keep event loop alive
    setInterval(() => {
      if (!tunnel.clientId) {
        console.log('Tunnel lost client ID, exiting...');
        process.exit(1);
      }
    }, 5000);

  } catch (err) {
    console.error('Error starting tunnel:', err);
    process.exit(1);
  }
})();
