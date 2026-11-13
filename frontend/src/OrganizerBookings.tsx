import { useListOrganizerBookings } from './api/generated/calendar';

function formatMoment(instant: string, timezone: string) {
  return new Intl.DateTimeFormat('ru-RU', { timeZone: timezone, year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'longOffset' }).format(new Date(instant));
}

export function OrganizerBookings() {
  const meetings = useListOrganizerBookings({
    request: { cache: 'no-store' },
    query: { staleTime: 0, refetchOnMount: 'always', refetchOnWindowFocus: true },
  });
  return (
    <main className="workspace container" id="main-content" tabIndex={-1}>
      <h1>Предстоящие встречи</h1>
      <p className="page-intro">Предстоящие встречи по всем событиям. Время указано в часовом поясе календаря</p>
      {meetings.isFetching && <p role="status">Загружаем встречи…</p>}
      {meetings.isError && <div role="alert"><p>Не удалось загрузить встречи. Повторите загрузку.</p><button className="button" onClick={() => void meetings.refetch()}>Повторить загрузку</button></div>}
      {meetings.isSuccess && <>
        <button className="button" disabled={meetings.isFetching} onClick={() => void meetings.refetch()}>Обновить встречи</button>
        {meetings.data.items.length === 0 ? <p className="empty-state">Предстоящих встреч пока нет.</p> : <div className="meeting-list">{meetings.data.items.map((booking) => <article className="event-card" key={booking.id}>
          <h2>{booking.eventType.name}</h2>
          <p>{booking.eventType.durationMinutes} минут</p>
          <p>Начало: <time dateTime={booking.startsAt}>{formatMoment(booking.startsAt, booking.timezone)}</time></p>
          <p>Окончание: <time dateTime={booking.endsAt}>{formatMoment(booking.endsAt, booking.timezone)}</time></p>
          <p>{booking.timezone}</p>
          <p>Гость: {booking.guest.name}</p>
          <p>Email: <a href={`mailto:${booking.guest.email}`}>{booking.guest.email}</a></p>
          <p className="event-description">Комментарий: {booking.guest.comment || '—'}</p>
        </article>)}</div>}
      </>}
    </main>
  );
}
