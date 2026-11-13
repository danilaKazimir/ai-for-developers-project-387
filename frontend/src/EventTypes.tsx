import { useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getListEventTypesQueryKey, useCreateEventType, useListEventTypes } from './api/generated/calendar';
import { ApiHttpError } from './api/http';
import { CopyGuestLink } from './CopyGuestLink';

export function EventTypeCatalog() {
  const catalog = useListEventTypes();
  return (
    <main className="workspace container" id="main-content" tabIndex={-1}>
      <h1>События</h1>
      <p className="page-intro">Отправьте гостю ссылку на событие — он выберет удобное время и запишется</p>
      {catalog.isPending && <p role="status">Загружаем события…</p>}
      {catalog.isError && <div role="alert"><p>Не удалось загрузить события. Повторите загрузку.</p><button className="button" onClick={() => void catalog.refetch()}>Повторить загрузку</button></div>}
      {catalog.isSuccess && (catalog.data.items.length === 0
        ? <p className="empty-state">Событий пока нет. Создайте первое событие и отправьте ссылку гостю.</p>
        : <div className="event-grid">{catalog.data.items.map((type) => (
          <article className="event-card" key={type.id}>
            <h2>{type.name}</h2>
            <p className="event-description">{type.description}</p>
            <p>{type.durationMinutes} минут</p>
            <CopyGuestLink eventTypeId={type.id} />
          </article>
        ))}</div>)}
      <a className="text-link" href="/">Вернуться на главную</a>
    </main>
  );
}

function creationError(error: unknown): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 422) return 'Проверьте поля: название, описание и целую длительность от 1 до 540 минут.';
    if (error.status === 503) return 'Сервис временно недоступен. Повторите попытку позже';
  }
  return 'Не удалось получить подтверждение создания. Проверьте список событий перед повторной отправкой.';
}

export function CreateEventType() {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [duration, setDuration] = useState('30');
  const queryClient = useQueryClient();
  const creation = useCreateEventType({
    mutation: {
      retry: false,
      onSuccess: () => { void queryClient.invalidateQueries({ queryKey: getListEventTypesQueryKey() }); },
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    creation.mutate({ data: { name: name.trim(), description, durationMinutes: Number(duration) } });
  }

  return (
    <main className="workspace container" id="main-content" tabIndex={-1}>
      <h1>Создать событие</h1>
      <p className="page-intro">Укажите название, описание и длительность встречи. После создания отправьте ссылку гостю</p>
      <p>Расписание: будни, 09:00–18:00, Europe/Moscow.</p>
      <form className="event-form" onSubmit={submit}>
        <label>Название
          <input readOnly={creation.isPending} required pattern="\s*\S(?:[\s\S]{0,118}\S)?\s*" title="Название: 1–120 символов без крайних пробелов" value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label htmlFor="event-description">Описание</label>
        <textarea readOnly={creation.isPending} id="event-description" maxLength={2000} rows={4} value={description} onChange={(event) => setDescription(event.target.value)} />
        <label>Длительность, минут
          <input readOnly={creation.isPending} type="number" required min={1} max={540} step={1} value={duration} onChange={(event) => setDuration(event.target.value)} />
        </label>
        {creation.isError && <p role="alert" className="form-error">{creationError(creation.error)}</p>}
        <button className="button button-primary" disabled={creation.isPending} type="submit">{creation.isPending ? 'Создаём…' : 'Создать событие'}</button>
      </form>
      {creation.isSuccess && <section className="creation-success" role="status" aria-live="polite">
        <h2>Событие создано</h2>
        <p>{creation.data.name} · {creation.data.durationMinutes} минут</p>
        <CopyGuestLink key={creation.data.id} eventTypeId={creation.data.id} />
        <p className="public-url">{window.location.origin}/event-types/{creation.data.id}</p>
        <a className="text-link" href="/event-types">К событиям</a>
      </section>}
      <a className="text-link" href="/">Вернуться на главную</a>
    </main>
  );
}
