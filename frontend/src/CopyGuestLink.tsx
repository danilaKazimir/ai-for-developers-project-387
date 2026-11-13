import { useId, useState } from 'react';

export function CopyGuestLink({ eventTypeId }: { eventTypeId: string }) {
  const inputId = useId();
  const [state, setState] = useState<'idle' | 'copying' | 'copied' | 'error'>('idle');
  const url = new URL(`/event-types/${eventTypeId}`, window.location.origin).href;

  async function copy() {
    setState('copying');
    try {
      await navigator.clipboard.writeText(url);
      setState('copied');
    } catch {
      setState('error');
    }
  }

  return (
    <div className="share-link">
      <button type="button" className="text-link" disabled={state === 'copying'} onClick={() => void copy()}>Скопировать ссылку</button>
      <span className="copy-feedback" aria-live="polite">{state === 'copied' ? 'Ссылка скопирована' : ''}</span>
      {state === 'error' && <div>
        <p role="alert">Не удалось скопировать автоматически. Скопируйте ссылку вручную</p>
        <label htmlFor={inputId}>Ссылка для гостя</label>
        <input id={inputId} type="text" readOnly value={url} onFocus={(event) => event.currentTarget.select()} />
      </div>}
    </div>
  );
}
