try {
  var theme = localStorage.getItem('health-chatbot.theme');
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
} catch {}
