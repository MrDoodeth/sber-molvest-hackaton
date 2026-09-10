import UserDialogsNav from "./UserDialogsNav";

export default function UserHomePage() {
  return (
    <div className="flex h-[calc(100vh-65px)] min-h-[32rem]">
      <div className="w-full md:hidden"><UserDialogsNav mobile /></div>
    </div>
  );
}
