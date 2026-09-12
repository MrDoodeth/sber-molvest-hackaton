import {
  ArrowRight,
  BookOpen,
  Check,
  Headphones,
  Image,
  MessageCircleMore,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Modal } from "../shared/ui";

const logoUrl = "/molvest-logo.png";

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-3 text-left">
      <span className="size-10 shrink-0 overflow-hidden rounded-xl bg-gradient-to-br from-molvest-400 to-[#fbc4fb]">
        <img className="size-full object-cover" src={logoUrl} alt="Молвест" />
      </span>
      <span>
        <strong className="block text-sm tracking-[0.06em] text-black">МОЛВЕСТ</strong>
        {!compact && <span className="mt-0.5 block text-[10px] font-medium uppercase tracking-[0.17em] text-slate-500">Поддержка 1С</span>}
      </span>
    </span>
  );
}

const benefits = [
  { title: "Ответы по базе знаний", text: "AI ищет решение в актуальных регламентах и документации 1С.", icon: BookOpen, tone: "bg-molvest-100 text-molvest-700" },
  { title: "Разбор скриншотов", text: "Можно показать ошибку интерфейса, а не переписывать её вручную.", icon: Image, tone: "bg-[#fbc4fb]/55 text-[#a13cc9]" },
  { title: "Специалист подключается сам", text: "Пользователь не выбирает линию поддержки, маршрутизацию делает агент.", icon: Headphones, tone: "bg-[#fcc67f]/45 text-[#9a5600]" },
];

const steps = [
  { title: "Пользователь задаёт вопрос", text: "Пишет проблему по 1С и при необходимости добавляет скриншот или файл.", icon: MessageCircleMore, tone: "bg-molvest-100 text-molvest-700" },
  { title: "AI ищет решение", text: "RAG-агент поднимает релевантные материалы, формирует ответ и оценивает confidence.", icon: Sparkles, tone: "bg-[#fbc4fb]/55 text-[#a13cc9]" },
  { title: "При необходимости - человек", text: "Если кейс сложный, обращение автоматически попадает оператору с полной историей.", icon: Headphones, tone: "bg-[#fcc67f]/45 text-[#9a5600]" },
];

export default function RoleSelectionPage() {
  const [staffOpen, setStaffOpen] = useState(false);

  return (
    <main className="min-h-screen overflow-x-hidden bg-[#f7f9fd] text-black">
      <header className="sticky top-0 z-30 border-b border-[#dbe3f0]/85 bg-[#f7f9fd]/92 backdrop-blur-xl">
        <div className="mx-auto flex h-[66px] w-[min(1180px,calc(100%-28px))] items-center gap-3 sm:h-[76px] sm:gap-7">
          <Link to="/" aria-label="Молвест - поддержка 1С"><Brand /></Link>
          <nav className="ml-4 hidden items-center gap-6 md:flex" aria-label="Навигация по странице">
            <a className="text-sm font-bold text-slate-600 transition hover:text-molvest-700" href="#how">Как это работает</a>
            <a className="text-sm font-bold text-slate-600 transition hover:text-molvest-700" href="#capabilities">Возможности</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button className="hidden rounded-lg px-3 py-2 text-sm font-bold text-slate-600 transition hover:bg-[#edf3fb] hover:text-black sm:block" type="button" onClick={() => setStaffOpen(true)}>
              Вход для команды
            </button>
            <Link className="rounded-xl bg-molvest-400 px-3 py-2.5 text-xs font-bold text-white transition hover:brightness-95 sm:px-4 sm:text-sm" to="/user">
              Задать вопрос
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto w-[min(1180px,calc(100%-28px))] pb-12 pt-8 sm:pb-16 sm:pt-14">
        <section className="grid items-center gap-8 lg:min-h-[540px] lg:grid-cols-[1.03fr_.97fr] lg:gap-16">
          <div className="py-2 sm:py-6">
            <span className="inline-flex items-center gap-2 rounded-full border border-molvest-400/20 bg-molvest-100 px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.15em] text-molvest-700">
              <span className="size-1.5 rounded-full bg-molvest-400" />AI-поддержка сотрудников
            </span>
            <h1 className="mt-5 max-w-[700px] text-4xl font-extrabold leading-[1.02] tracking-[-0.045em] sm:text-5xl lg:text-[58px]">
              Вопрос по 1С? <span className="text-molvest-700">Спросите здесь.</span>
            </h1>
            <p className="mt-5 max-w-[620px] text-[15px] leading-7 text-slate-500 sm:text-[17px] sm:leading-8">
              Опишите проблему своими словами или приложите скриншот. AI-агент проверит базу знаний «Молвест», предложит решение и подключит специалиста, если вопрос требует человека.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link className="inline-flex items-center justify-center gap-2 rounded-[13px] bg-molvest-400 px-5 py-3.5 text-sm font-bold text-white transition hover:brightness-95" to="/user">
                <MessageCircleMore className="size-[17px]" />Задать вопрос
              </Link>
              <a className="inline-flex items-center justify-center rounded-[13px] border border-[#dbe3f0] bg-white px-5 py-3.5 text-sm font-bold transition hover:border-molvest-400 hover:text-molvest-700" href="#how">
                Как работает поддержка
              </a>
            </div>
            <div className="mt-6 flex flex-col gap-2 text-xs font-semibold text-slate-500 sm:flex-row sm:flex-wrap sm:gap-x-5">
              {["Без выбора роли", "История остаётся в одном чате", "Можно приложить файл или скриншот"].map((item) => <span key={item} className="flex items-center gap-1.5"><Check className="size-4 text-molvest-700" />{item}</span>)}
            </div>
          </div>

          <div className="relative min-h-[390px] overflow-hidden rounded-[28px] bg-[#0c1220] p-4 shadow-[0_30px_70px_rgba(31,58,100,.18)] sm:min-h-[440px] sm:p-[22px]">
            <div className="absolute -right-20 -top-20 size-64 rounded-full bg-molvest-400/25 blur-2xl" aria-hidden="true" />
            <div className="absolute -bottom-24 -left-20 size-56 rounded-full bg-[#fbc4fb]/20 blur-2xl" aria-hidden="true" />
            <div className="relative flex items-center justify-between text-white">
              <strong className="flex items-center gap-2.5 text-sm"><span className="size-2 rounded-full bg-[#77d8a6] shadow-[0_0_0_5px_rgba(119,216,166,.12)]" />AI-поддержка 1С</strong>
              <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#8ea3c8]">онлайн</span>
            </div>
            <div className="relative mt-5 flex min-h-[294px] flex-col gap-3 rounded-[20px] bg-[#f7f9fd] p-4 sm:min-h-[330px] sm:p-5">
              <p className="ml-auto max-w-[88%] rounded-[15px] rounded-br-md bg-molvest-400 px-3.5 py-3 text-[13px] leading-5 text-white">Не проводится документ реализации. Что проверить?</p>
              <p className="max-w-[88%] rounded-[15px] rounded-bl-md border border-[#dbe3f0] bg-white px-3.5 py-3 text-[13px] leading-5">Проверю регламент и связанные ошибки в базе знаний. Начните с остатков по партии и статуса «Выработки продукции».</p>
              <div className="flex flex-wrap gap-1.5"><span className="rounded-full bg-molvest-100 px-2 py-1 text-[10px] font-extrabold text-molvest-700">RAG · база знаний</span><span className="rounded-full bg-molvest-100 px-2 py-1 text-[10px] font-extrabold text-molvest-700">Confidence 86%</span></div>
              <p className="max-w-[88%] rounded-[15px] rounded-bl-md border border-[#dbe3f0] bg-white px-3.5 py-3 text-[13px] leading-5">Если данных будет недостаточно, я передам этот же диалог специалисту.</p>
              <div className="mt-auto flex items-center gap-2 rounded-[14px] border border-[#dbe3f0] bg-white py-2 pl-3 text-xs text-slate-400"><span className="flex-1">Опишите вопрос по 1С...</span><Link className="mr-2 grid size-[34px] place-items-center rounded-[10px] bg-molvest-400 text-white" to="/user" aria-label="Задать вопрос"><Send className="size-4" /></Link></div>
            </div>
          </div>
        </section>

        <section id="capabilities" className="mt-6 grid gap-3 lg:grid-cols-3">
          {benefits.map(({ title, text, icon: Icon, tone }) => <article key={title} className="flex gap-3 rounded-[17px] border border-[#dbe3f0] bg-white p-4 shadow-[0_5px_18px_rgba(20,40,80,.04)]"><span className={`grid size-10 shrink-0 place-items-center rounded-xl ${tone}`}><Icon className="size-[18px]" /></span><div><h2 className="text-sm font-bold">{title}</h2><p className="mt-1 text-xs leading-5 text-slate-500">{text}</p></div></article>)}
        </section>

        <section id="how" className="mt-16 scroll-mt-24 sm:mt-24">
          <div className="max-w-2xl"><span className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-molvest-700">Один сценарий для пользователя</span><h2 className="mt-3 text-3xl font-extrabold tracking-[-0.025em] sm:text-[34px]">Не нужно разбираться, кому писать</h2><p className="mt-3 text-sm leading-6 text-slate-500">Откройте поддержку, задайте вопрос и продолжайте диалог. Решение о подключении оператора принимает система по контексту и уверенности ответа.</p></div>
          <div className="mt-7 grid gap-4 md:grid-cols-3">
            {steps.map(({ title, text, icon: Icon, tone }, index) => <article key={title} className="relative min-h-[210px] overflow-hidden rounded-[20px] border border-[#dbe3f0] bg-white p-5 sm:p-[22px]"><span className="text-[11px] font-extrabold tracking-[0.16em] text-molvest-700">ШАГ 0{index + 1}</span><span className={`absolute right-5 top-5 grid size-[42px] place-items-center rounded-[13px] ${tone}`}><Icon className="size-5" /></span><h3 className="mt-8 text-lg font-bold">{title}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{text}</p></article>)}
          </div>
          <div className="mt-6 flex flex-col gap-5 rounded-[22px] bg-gradient-to-br from-[#0c1220] to-[#17253e] p-6 text-white sm:flex-row sm:items-center sm:px-8"><div><h2 className="text-xl font-bold">Есть вопрос по 1С?</h2><p className="mt-1 text-sm text-[#a9b7cf]">Начните с одного сообщения, дальше поддержку маршрутизирует система.</p></div><Link className="inline-flex items-center justify-center gap-2 rounded-xl bg-molvest-400 px-5 py-3 text-sm font-bold transition hover:brightness-95 sm:ml-auto" to="/user">Открыть поддержку<ArrowRight className="size-4" /></Link></div>
        </section>
      </div>

      <footer className="border-t border-[#dbe3f0] bg-white"><div className="mx-auto flex w-[min(1180px,calc(100%-28px))] flex-wrap items-center gap-4 py-6 sm:min-h-[118px]"><Brand compact /><button className="rounded-lg p-2 text-xs font-bold text-slate-500 transition hover:bg-slate-100 hover:text-black" type="button" onClick={() => setStaffOpen(true)}>Служебный вход</button><p className="w-full text-xs leading-5 text-slate-500 sm:ml-auto sm:w-auto sm:text-right">Демонстрационный контур<br />Данные и сценарии используются для прототипа</p></div></footer>

      <Modal open={staffOpen} title="Вход для команды поддержки" description="Служебные рабочие места отделены от пользовательского сценария." onClose={() => setStaffOpen(false)}>
        <div className="grid gap-3">
          <Link className="group flex items-center gap-3 rounded-2xl border border-[#dbe3f0] p-3.5 transition hover:border-molvest-400 hover:shadow-lg" to="/operator" onClick={() => setStaffOpen(false)}><span className="grid size-11 place-items-center rounded-xl bg-[#fbc4fb]/55 text-[#a13cc9]"><Headphones className="size-5" /></span><span className="flex-1"><strong className="block text-sm">Оператор</strong><span className="mt-0.5 block text-xs text-slate-500">Очередь эскалаций и ответы пользователям</span></span><ArrowRight className="size-5 text-slate-300 transition group-hover:translate-x-1 group-hover:text-molvest-700" /></Link>
          <Link className="group flex items-center gap-3 rounded-2xl border border-[#dbe3f0] p-3.5 transition hover:border-molvest-400 hover:shadow-lg" to="/admin/dialogs" onClick={() => setStaffOpen(false)}><span className="grid size-11 place-items-center rounded-xl bg-[#fcc67f]/45 text-[#9a5600]"><ShieldCheck className="size-5" /></span><span className="flex-1"><strong className="block text-sm">Администратор</strong><span className="mt-0.5 block text-xs text-slate-500">База знаний, настройки AI и мониторинг</span></span><ArrowRight className="size-5 text-slate-300 transition group-hover:translate-x-1 group-hover:text-molvest-700" /></Link>
        </div>
      </Modal>
    </main>
  );
}
