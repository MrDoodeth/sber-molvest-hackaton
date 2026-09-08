import { Bot, Image, MessageCircleMore, ShieldCheck } from "lucide-react";
import UserDialogsNav from "./UserDialogsNav";

export default function UserHomePage() {
  return (
    <div className="flex h-[calc(100vh-65px)] min-h-[32rem]">
      <div className="w-full md:hidden"><UserDialogsNav mobile /></div>
      <UserDialogsNav />
      <section className="relative hidden min-w-0 flex-1 items-center justify-center overflow-hidden bg-cream p-8 md:flex">
        <div className="max-w-2xl text-center">
          <span className="mx-auto flex size-16 items-center justify-center rounded-[1.4rem] bg-molvest-400 text-white shadow-xl"><MessageCircleMore className="size-7" /></span>
          <h1 className="mt-6 text-3xl font-black tracking-[-0.025em] text-black">Поддержка 1С в одном диалоге</h1>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-7 text-slate-500">Выберите обращение слева или создайте новый чат. Если GigaChat не уверен в решении, к этой же переписке подключится специалист.</p>
          <div className="mt-8 grid gap-3 text-left sm:grid-cols-3">
            <div className="rounded-2xl border border-[#dbe3f0] bg-white p-4 shadow-sm"><Bot className="size-5 text-molvest-700" /><strong className="mt-3 block text-sm">Ответ по БЗ</strong><span className="mt-1 block text-xs leading-5 text-slate-500">Инструкции и документы 1С</span></div>
            <div className="rounded-2xl border border-[#dbe3f0] bg-white p-4 shadow-sm"><Image className="size-5 text-[#a13cc9]" /><strong className="mt-3 block text-sm">Файлы ошибки</strong><span className="mt-1 block text-xs leading-5 text-slate-500">До 10 файлов в сообщении</span></div>
            <div className="rounded-2xl border border-[#dbe3f0] bg-white p-4 shadow-sm"><ShieldCheck className="size-5 text-[#9a5600]" /><strong className="mt-3 block text-sm">Живой оператор</strong><span className="mt-1 block text-xs leading-5 text-slate-500">Без нового тикета</span></div>
          </div>
        </div>
      </section>
    </div>
  );
}
