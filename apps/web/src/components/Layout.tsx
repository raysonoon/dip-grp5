import { useEffect, useRef, useState } from "react";
import { Outlet } from "react-router-dom";
import { RotateCcw, RotateCw, Send, Square, X } from "lucide-react";
import ChatMessageContent from "./ChatMessageContent";
import { useChat as useChatUI } from "../contexts/ChatContext";
import { useChatSession } from "../hooks/useChatSession";
import Footer from "./Footer";
import Header from "./Header";
import VendorWheel from "./VendorWheel";

// -------------------------------------------------------------
// 1. Floating Foodie Chatbot Component
// -------------------------------------------------------------
const MASCOT_GREETINGS = ["Hey hey! 👋", "Ready to makan? 🍜", "You found me! ✨"];

export function FoodieChat() {
  const {
    input: chatInput,
    isGenerating: isTyping,
    messages: chatMessages,
    sendMessage,
    setInput: setChatInput,
    startNewSession: startNewChat,
    stopResponse,
    wheelVendors,
    removeWheelVendor,
  } = useChatSession();
  const { chatOpen, closeChat, toggleChat } = useChatUI();
  const [wheelOpen, setWheelOpen] = useState(false);
  const [greetingCount, setGreetingCount] = useState(0);
  const [showGreeting, setShowGreeting] = useState(false);
  const greetingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (greetingTimer.current) clearTimeout(greetingTimer.current);
  }, []);

  function greet() {
    if (greetingTimer.current) clearTimeout(greetingTimer.current);
    setGreetingCount((count) => count + 1);
    setShowGreeting(true);
    greetingTimer.current = setTimeout(() => setShowGreeting(false), 2200);
  }

  return (
    <div className="fixed bottom-4 right-4 sm:bottom-6 sm:right-6 z-50 flex flex-col items-end gap-3">
      {chatOpen && (
        <div data-chat-window className="w-[calc(100vw-2rem)] sm:w-[360px] rounded-2xl border border-border bg-card shadow-2xl overflow-hidden">
          {/* Chat Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-primary text-white">
            <div className="flex items-center gap-3">
              {/* White Circular Background Behind Mascot in Header */}
              <div className="relative flex-shrink-0">
                <button
                  type="button"
                  onClick={greet}
                  aria-label="Say hi to Foodie"
                  className="block cursor-pointer"
                >
                  <div className="w-9 h-9 rounded-full bg-white overflow-hidden flex items-center justify-center shadow-md">
                    <img
                      key={greetingCount}
                      src="/ntummy_mascot_head.svg"
                      alt="NTUmmy Mascot"
                      className={`w-full h-full mt-1 object-contain ${showGreeting ? "animate-[foodie-hello_0.8s_ease-in-out_both]" : isTyping ? "animate-[foodie-talk_0.7s_ease-in-out_infinite_alternate]" : ""}`}
                    />
                  </div>
                </button>
                {showGreeting && (
                  <span
                    role="status"
                    className="absolute top-full left-0 mt-2 z-10 w-max max-w-[150px] rounded-md rounded-tl-sm border border-line-warm bg-surface-warm px-2 py-1 text-[11px] font-semibold text-ink shadow-md"
                  >
                    {MASCOT_GREETINGS[(greetingCount - 1) % MASCOT_GREETINGS.length]}
                  </span>
                )}
              </div>
              <div>
                <div className="text-sm font-bold text-white leading-tight">Foodie <span aria-hidden="true" className="ml-1 text-[#dc9a27]">✦</span></div>
                <div className="text-xs text-white/75 font-medium">Your campus makan buddy</div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => { setWheelOpen(false); startNewChat(); }}
                className="text-white/75 hover:text-white transition-colors p-1"
                aria-label="Start a new chat session"
                title="New chat"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={closeChat}
                className="text-white/75 hover:text-white transition-colors p-1"
                aria-label="Close chat"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Chat Messages */}
          <div className="p-4 h-72 overflow-y-auto flex flex-col gap-3 bg-background">
            {chatMessages.length === 1 && (
              <button
                type="button"
                onClick={greet}
                aria-label="Give Foodie a wave"
                className="relative mx-auto mb-1 flex h-24 w-24 items-center justify-center cursor-pointer"
              >
                <img
                  key={greetingCount}
                  src="/ntummy_mascot.svg"
                  alt=""
                  aria-hidden="true"
                  className="h-full w-auto object-contain mix-blend-multiply animate-[foodie-hello_0.8s_ease-in-out_both]"
                />
                <span aria-hidden="true" className="absolute -right-2 top-1 text-xl text-[#dc9a27]">✦</span>
                <span
                  key={`wave-${greetingCount}`}
                  aria-hidden="true"
                  className="absolute -left-3 top-3 text-lg origin-bottom animate-[foodie-wave_0.6s_ease-in-out_3_alternate]"
                >
                  👋
                </span>
              </button>
            )}
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[82%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground rounded-br-none"
                      : "bg-card border border-border text-foreground rounded-bl-none"
                  }`}
                >
                  {msg.role === "bot" ? (
                    <ChatMessageContent answer={msg.text} sources={msg.sources} />
                  ) : (
                    msg.text
                  )}
                </div>
              </div>
            ))}
            {isTyping && (
              <div className="flex justify-start">
                <div className="px-4 py-3 rounded-2xl bg-card border border-border rounded-bl-none">
                  <div className="flex gap-1 items-center">
                    {[0, 1, 2].map((i) => (
                      <div
                        key={i}
                        className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {wheelVendors.length >= 2 && <button type="button" className="vendor-wheel-invite" disabled={isTyping} onClick={() => setWheelOpen(true)}><RotateCw size={15} aria-hidden="true" /> Spin the wheel <span>{wheelVendors.length} places</span></button>}

          {/* Chat Input */}
          <div className="px-4 py-4 border-t border-border bg-card">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendMessage(chatInput)}
                placeholder="What are you craving today?"
                className="flex-1 bg-background border border-border rounded-xl px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40 transition-colors"
              />
              {isTyping ? (
                <button
                  type="button"
                  onClick={stopResponse}
                  aria-label="Stop generating response"
                  title="Stop"
                  className="w-10 h-10 rounded-xl bg-destructive text-destructive-foreground flex items-center justify-center hover:opacity-90 transition-opacity flex-shrink-0"
                >
                  <Square className="w-4 h-4 fill-current" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => sendMessage(chatInput)}
                  disabled={!chatInput.trim()}
                  aria-label="Send message"
                  className="w-10 h-10 rounded-xl bg-[#B22222] text-white flex items-center justify-center hover:opacity-90 disabled:opacity-50 transition-opacity flex-shrink-0"
                >
                  <Send className="w-4 h-4 text-white" />
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {wheelOpen && <VendorWheel vendors={wheelVendors} onRemove={removeWheelVendor} onClose={() => setWheelOpen(false)} />}

      {/* Chat Toggle Button with White Circle Behind Mascot */}
      <button
        type="button"
        onClick={toggleChat}
        aria-label="Open Foodie chatbot"
        className="group flex items-center gap-2.5 rounded-full border border-white/15 bg-primary px-4 py-2 text-primary-foreground shadow-lg cursor-pointer transition-all duration-200 hover:-translate-y-0.5 active:translate-y-0"
      >
        {chatOpen ? (
          <X className="h-5 w-5" />
        ) : (
          <>
            <div className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full bg-white shadow-sm">
              <img
                src="/ntummy_mascot_head.svg"
                alt="NTUmmy Mascot"
                className="h-full w-full mt-0.5 object-contain"
              />
            </div>
            <span className="flex flex-col text-left leading-tight">
              <strong className="text-[13px] font-bold">Time to eat?</strong>
              <small className="text-[11px] text-white/75">Ask Foodie</small>
            </span>
          </>
        )}
      </button>
    </div>
  );
}

// -------------------------------------------------------------
// 2. Shared Layout Component
// -------------------------------------------------------------
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