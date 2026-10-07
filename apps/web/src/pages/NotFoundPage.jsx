import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-6">
      <div className="text-center max-w-md">
        <p className="text-primary text-sm font-bold uppercase tracking-widest mb-3">
          Error 404
        </p>

        <h1 className="text-5xl md:text-6xl font-bold font-display mb-4">
          Page Not Found
        </h1>

        <p className="text-muted-foreground leading-relaxed mb-8">
          Sorry, we couldn't find the page you're looking for. It may have
          been moved or the URL may be incorrect.
        </p>

        <Link
          to="/"
          className="inline-flex items-center justify-center px-5 py-3 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 transition-opacity"
        >
          Back to Home
        </Link>
      </div>
    </div>
  );
}
