import { Outlet } from "react-router-dom";
import FoodieChat from "./FoodieChat";
import Footer from "./Footer";
import Header from "./Header";

export { FoodieChat };

type LayoutProps = {
  preferenceStatus: "pending" | "completed" | "skipped" | null;
  openPreferences: () => void;
};

export default function Layout({
  preferenceStatus,
  openPreferences,
}: LayoutProps) {
  return (
    <div className="min-h-screen supports-[height:100dvh]:min-h-dvh flex flex-col bg-background text-foreground font-sans">
      <Header />

      <main className="flex-1">
        <Outlet
          context={{
            preferenceStatus,
            openPreferences,
          }}
        />
      </main>

      <Footer />
    </div>
  );
}
