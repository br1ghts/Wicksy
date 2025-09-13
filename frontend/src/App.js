import React, { useEffect, useState } from 'react';

function App() {
  const [watchlist, setWatchlist] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [trades, setTrades] = useState([]);

  useEffect(() => {
    fetch('/watchlist').then(res => res.json()).then(setWatchlist).catch(console.error);
    fetch('/alerts').then(res => res.json()).then(setAlerts).catch(console.error);
    fetch('/trades').then(res => res.json()).then(setTrades).catch(console.error);
  }, []);

  return (
    <div>
      <h1>Wicksy React Frontend</h1>
      <pre>{JSON.stringify({ watchlist, alerts, trades }, null, 2)}</pre>
    </div>
  );
}

export default App;
