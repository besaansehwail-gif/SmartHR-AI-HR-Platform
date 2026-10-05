import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import {LocaleProvider} from './i18n';
import './index.css';

/*
  LocaleProvider wraps <App /> rather than living inside it, for two reasons:
  the language switcher has to work on the sign-in screen, before there is a
  session; and signing in replaces the whole authenticated tree, which would
  reset a provider mounted below it.
*/
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LocaleProvider>
      <App />
    </LocaleProvider>
  </StrictMode>,
);
