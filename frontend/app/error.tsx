"use client";

import React, { useEffect } from "react";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";
import Link from "next/link";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[Pannaga Error Boundary Caught]:", error);
  }, [error]);

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6 font-sans"
    >
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl text-center space-y-4">
        <div className="w-12 h-12 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center mx-auto">
          <AlertTriangle className="w-6 h-6" />
        </div>

        <div>
          <h2 className="text-lg font-bold text-white">Something went wrong</h2>
          <p className="text-xs text-slate-400 mt-1">
            An unexpected error occurred while processing the monsoon forecast.
          </p>
        </div>

        {error.message && (
          <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 text-left font-mono text-[11px] text-rose-300 break-all">
            {error.message}
          </div>
        )}

        <div className="flex items-center justify-center space-x-3 pt-2">
          <button
            onClick={() => reset()}
            className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold flex items-center space-x-1.5 transition-colors shadow-lg"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Try Again</span>
          </button>

          <Link
            href="/"
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center space-x-1.5 transition-colors border border-slate-700"
          >
            <Home className="w-3.5 h-3.5" />
            <span>Go Home</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
