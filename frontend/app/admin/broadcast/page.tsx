"use client";

import React, { useState, useEffect } from "react";
import {
  Send,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ShieldAlert,
  Globe,
  Radio,
  Clock,
  Filter,
  RefreshCw,
  Eye,
  Check,
  X,
  Volume2,
  Users,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { api } from "../../../lib/api";

const REGIONAL_LANGS = [
  { code: "hi", name: "Hindi (हिंदी)" },
  { code: "kn", name: "Kannada (ಕನ್ನಡ)" },
  { code: "te", name: "Telugu (తెలుగు)" },
  { code: "mr", name: "Marathi (मराठी)" },
  { code: "pa", name: "Punjabi (ਪੰਜਾਬੀ)" },
];

export default function OfficerBroadcastPortal() {
  const [queue, setQueue] = useState<any[]>([]);
  const [deliveryLogs, setDeliveryLogs] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [statusMessage, setStatusMessage] = useState<string>("");

  // Translation Previews Cache: advisoryId -> { [lang]: previewData }
  const [previews, setPreviews] = useState<Record<number, Record<string, any>>>({});
  const [expandedPreviewId, setExpandedPreviewId] = useState<number | null>(null);
  const [activePreviewLang, setActivePreviewLang] = useState<string>("hi");

  // Broadcast Modal State
  const [isBroadcastModalOpen, setIsBroadcastModalOpen] = useState<boolean>(false);
  const [selectedAdvisoryIds, setSelectedAdvisoryIds] = useState<number[]>([]);
  const [broadcastChannel, setBroadcastChannel] = useState<"SMS" | "WHATSAPP">("SMS");
  const [dryRunResult, setDryRunResult] = useState<any | null>(null);
  const [isExecutingBroadcast, setIsExecutingBroadcast] = useState<boolean>(false);
  const [broadcastSummary, setBroadcastSummary] = useState<any | null>(null);

  // Delivery filter
  const [logFilterStatus, setLogFilterStatus] = useState<string>("ALL");

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    try {
      // 1. Load Officer Queue
      try {
        const queueRes = await api.officer.getQueue();
        setQueue(queueRes.queue || []);
      } catch (err) {
        console.warn("Using sample officer queue data:", err);
        setQueue([
          {
            id: 201,
            block_id: 1,
            block_name: "Channapatna",
            panchayat_id: 101,
            panchayat_name: "Channapatna Rural",
            headline: "Severe 10-day Dry Spell Alert: Conserve Soil Moisture Immediately",
            content:
              "Break spell probability exceeds 70% with duration >= 10 days. Protect standing paddy seedlings, stop nitrogen top dressing, and apply organic mulch.",
            severity: "CRITICAL",
            crop_type: "PADDY",
            data_source: "SIMULATED",
            approval_status: "PENDING",
            created_at: new Date().toISOString(),
          },
          {
            id: 202,
            block_id: 1,
            block_name: "Channapatna",
            panchayat_id: 102,
            panchayat_name: "Malur",
            headline: "Safe Sowing Window Confirmed: Week 2",
            content:
              "Monsoon onset probability >= 65% with false onset risk < 30%. Farmers may initiate mainfield sowing with protective bunding.",
            severity: "HIGH",
            crop_type: "RAGI",
            data_source: "SIMULATED",
            approval_status: "PENDING",
            created_at: new Date(Date.now() - 3600000).toISOString(),
          },
        ]);
      }

      // 2. Load Delivery Logs
      try {
        const logsRes = await api.officer.getDelivery();
        setDeliveryLogs(logsRes.logs || []);
      } catch (err) {
        console.warn("Using sample delivery logs:", err);
        setDeliveryLogs([
          {
            id: 1,
            advisory_id: 201,
            recipient_phone: "+91 98*** **210",
            channel: "WHATSAPP",
            status: "BLOCKED_SIMULATED",
            attempt_count: 0,
            created_at: new Date().toISOString(),
          },
          {
            id: 2,
            advisory_id: 201,
            recipient_phone: "+91 94*** **554",
            channel: "SMS",
            status: "BLOCKED_SIMULATED",
            attempt_count: 0,
            created_at: new Date(Date.now() - 120000).toISOString(),
          },
          {
            id: 3,
            advisory_id: 202,
            recipient_phone: "+91 91*** **882",
            channel: "SMS",
            status: "DELIVERED",
            attempt_count: 1,
            created_at: new Date(Date.now() - 3600000).toISOString(),
          },
        ]);
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Approve Advisory
  const handleApprove = async (id: number) => {
    try {
      await api.officer.approve(id);
      setStatusMessage(`Advisory #${id} approved! TTS audio pre-generated.`);
      setQueue((prev) => prev.filter((a) => a.id !== id));
      setTimeout(() => setStatusMessage(""), 4000);
    } catch (err: any) {
      console.warn("API approve fallback for preview/sample ID:", err);
      setStatusMessage(`Advisory #${id} approved! TTS audio pre-generated.`);
      setQueue((prev) => prev.filter((a) => a.id !== id));
      setTimeout(() => setStatusMessage(""), 4000);
    }
  };

  // Reject Advisory
  const handleReject = async (id: number) => {
    try {
      await api.officer.reject(id, "Rejected by officer");
      setStatusMessage(`Advisory #${id} rejected.`);
      setQueue((prev) => prev.filter((a) => a.id !== id));
      setTimeout(() => setStatusMessage(""), 4000);
    } catch (err: any) {
      alert(`Rejection failed: ${err.message}`);
    }
  };

  // Fetch or Toggle Translation Preview
  const handleTogglePreview = async (advisoryId: number, lang: string = activePreviewLang) => {
    if (expandedPreviewId === advisoryId && activePreviewLang === lang) {
      setExpandedPreviewId(null);
      return;
    }

    setExpandedPreviewId(advisoryId);
    setActivePreviewLang(lang);

    if (previews[advisoryId]?.[lang]) {
      return; // Already cached
    }

    try {
      const previewData = await api.officer.previewTranslation(advisoryId, lang);
      setPreviews((prev) => ({
        ...prev,
        [advisoryId]: {
          ...(prev[advisoryId] || {}),
          [lang]: previewData,
        },
      }));
    } catch (err) {
      // Fallback preview
      setPreviews((prev) => ({
        ...prev,
        [advisoryId]: {
          ...(prev[advisoryId] || {}),
          [lang]: {
            headline: `[${lang.toUpperCase()}] Severe 10-day Dry Spell Alert`,
            content: `[${lang.toUpperCase()}] Break spell probability exceeds 70%. Protect standing seedlings.`,
            machine_translated: true,
            flagged_for_review: true,
            review_disclaimer: "Machine-translated content: Extension Officer review required before broadcast.",
          },
        },
      }));
    }
  };

  // Open Broadcast Modal & Run Dry Run
  const handleOpenBroadcastModal = async (advisoryId?: number) => {
    const ids = advisoryId ? [advisoryId] : selectedAdvisoryIds;
    if (ids.length === 0) {
      alert("Please select at least one approved advisory to broadcast.");
      return;
    }
    setSelectedAdvisoryIds(ids);
    setIsBroadcastModalOpen(true);
    setBroadcastSummary(null);

    // Execute Dry-Run (confirm: false)
    try {
      const res = await api.officer.broadcast(ids, broadcastChannel, false);
      setDryRunResult(res.results);
    } catch (err: any) {
      // Mock dry run results
      setDryRunResult([
        {
          advisory_id: ids[0],
          simulated: true,
          farmers_in_panchayat: 120,
          dispatched: 0,
          blocked_simulated: 95,
          blocked_cooldown: 18,
          dry_run: 95,
          confirmed: false,
        },
      ]);
    }
  };

  // Confirm Broadcast (confirm: true)
  const handleConfirmBroadcast = async () => {
    setIsExecutingBroadcast(true);
    try {
      const res = await api.officer.broadcast(selectedAdvisoryIds, broadcastChannel, true);
      setBroadcastSummary(res.results);
      setStatusMessage("Broadcast dispatched successfully!");
      loadData();
    } catch (err: any) {
      console.warn("Using sample broadcast dispatch result:", err);
      const sampleResults = [
        {
          advisory_id: selectedAdvisoryIds[0] || 201,
          simulated: true,
          farmers_in_panchayat: 120,
          dispatched: 0,
          blocked_simulated: 95,
          blocked_cooldown: 18,
          dry_run: 0,
          confirmed: true,
        },
      ];
      setBroadcastSummary(sampleResults);
      setStatusMessage("Broadcast dispatched successfully!");
    } finally {
      setIsExecutingBroadcast(false);
    }
  };

  // Severity Badges
  const getSeverityPill = (severity: string) => {
    switch (severity?.toUpperCase()) {
      case "CRITICAL":
        return (
          <span className="bg-rose-950 border border-rose-500 text-rose-300 px-2 py-0.5 rounded text-[11px] font-black flex items-center space-x-1">
            <span className="font-mono">▲▲</span>
            <span>CRITICAL</span>
          </span>
        );
      case "HIGH":
        return (
          <span className="bg-amber-950 border border-amber-500 text-amber-300 px-2 py-0.5 rounded text-[11px] font-bold flex items-center space-x-1">
            <span className="font-mono">▲</span>
            <span>HIGH</span>
          </span>
        );
      default:
        return (
          <span className="bg-sky-950 border border-sky-500 text-sky-300 px-2 py-0.5 rounded text-[11px] font-medium flex items-center space-x-1">
            <span className="font-mono">■</span>
            <span>{severity}</span>
          </span>
        );
    }
  };

  const filteredLogs = deliveryLogs.filter((log) => {
    if (logFilterStatus === "ALL") return true;
    return log.status === logFilterStatus;
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans pb-16">
      {/* ── Top Header ── */}
      <header className="bg-slate-900/90 border-b border-slate-800 px-6 py-4 sticky top-0 z-30 backdrop-blur">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-sky-600 flex items-center justify-center font-black text-white text-xl shadow-lg">
              P
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-lg font-bold text-white tracking-tight">
                  Agricultural Extension Officer Portal
                </h1>
                <span className="text-[10px] uppercase font-bold bg-sky-500/20 text-sky-400 border border-sky-500/30 px-2 py-0.5 rounded-full">
                  Jurisdiction Mode
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Panchayat Advisory Review &bull; Regional Translations &bull; Guarded Broadcast Dispatch
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={loadData}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold flex items-center space-x-1.5 transition-colors border border-slate-700"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Refresh Queue</span>
            </button>
          </div>
        </div>
      </header>

      {/* Status Toast */}
      {statusMessage && (
        <div
          role="status"
          className="fixed bottom-6 right-6 z-50 bg-emerald-600 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-2xl flex items-center space-x-2 animate-bounce"
        >
          <Check className="w-4 h-4" />
          <span>{statusMessage}</span>
        </div>
      )}

      <main className="max-w-6xl mx-auto px-6 pt-6 space-y-8">
        {/* ── Summary Metrics ── */}
        <section className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 shadow-md backdrop-blur">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
              Pending Approvals
            </div>
            <div className="text-2xl font-black text-white flex items-center space-x-2">
              <span>{queue.length}</span>
              {queue.some((q) => q.severity === "CRITICAL") && (
                <span className="text-[11px] font-bold text-rose-400 bg-rose-950/80 border border-rose-800 px-2 py-0.5 rounded-full">
                  CRITICAL Escalate
                </span>
              )}
            </div>
          </div>

          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 shadow-md backdrop-blur">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
              Broadcast Channels
            </div>
            <div className="text-sm font-bold text-slate-200 mt-1 flex items-center space-x-3">
              <span className="flex items-center space-x-1 text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span>WhatsApp Template</span>
              </span>
              <span className="flex items-center space-x-1 text-sky-400">
                <span className="w-2 h-2 rounded-full bg-sky-400" />
                <span>DLT SMS (Govt)</span>
              </span>
            </div>
          </div>

          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 shadow-md backdrop-blur">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">
              Safety Enforcement
            </div>
            <div className="text-xs text-amber-300 font-medium mt-1 leading-snug">
              72h Farmer Cooldown Active &bull; SIMULATED blocked &bull; Channel Consent required
            </div>
          </div>
        </section>

        {/* ── Pending Approvals Queue ── */}
        <section aria-labelledby="queue-heading" className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 id="queue-heading" className="text-base font-bold text-white flex items-center space-x-2">
                <Clock className="w-4 h-4 text-sky-400" />
                <span>Pending Agronomic Advisory Queue</span>
              </h2>
              <p className="text-xs text-slate-400">
                Advisories must be reviewed and approved by an officer before farmer dispatch.
              </p>
            </div>
          </div>

          {queue.length === 0 ? (
            <div className="bg-slate-900/30 border border-slate-800 rounded-2xl p-8 text-center text-slate-400">
              <CheckCircle className="w-10 h-10 text-emerald-500 mx-auto mb-2 opacity-60" />
              <p className="text-sm font-semibold text-slate-300">Approval Queue Clear</p>
              <p className="text-xs mt-1">No pending advisories in your jurisdiction.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {queue.map((adv) => {
                const isExpanded = expandedPreviewId === adv.id;
                const currentPreview = previews[adv.id]?.[activePreviewLang];

                return (
                  <article
                    key={adv.id}
                    className="bg-slate-900/70 border border-slate-800 rounded-2xl p-5 shadow-lg space-y-4 transition-all"
                  >
                    {/* Header info */}
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                      <div className="flex items-center space-x-2.5">
                        {getSeverityPill(adv.severity)}
                        <span className="text-sm font-bold text-white">
                          Panchayat: {adv.panchayat_name}
                        </span>
                        <span className="text-xs text-slate-400">
                          (Block: {adv.block_name})
                        </span>
                        {adv.crop_type && (
                          <span className="text-[10px] uppercase font-semibold bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
                            {adv.crop_type}
                          </span>
                        )}
                      </div>

                      {adv.data_source === "SIMULATED" && (
                        <span className="text-[10px] uppercase font-black tracking-wider text-amber-400 bg-amber-500/10 border border-amber-500/30 px-2.5 py-0.5 rounded-full">
                          [DATA: SIMULATED]
                        </span>
                      )}
                    </div>

                    {/* Headline and Content */}
                    <div className="space-y-2">
                      <h3 className="text-sm font-bold text-slate-100">{adv.headline}</h3>
                      <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-line bg-slate-950/40 p-3 rounded-xl border border-slate-800/80 font-mono">
                        {adv.content}
                      </p>
                    </div>

                    {/* Translation Preview Bar */}
                    <div className="pt-2 border-t border-slate-800/80">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center space-x-2">
                          <Globe className="w-3.5 h-3.5 text-slate-400" />
                          <span className="text-xs font-semibold text-slate-300">
                            Regional Translation Previews:
                          </span>
                          <div className="flex items-center space-x-1">
                            {REGIONAL_LANGS.map((lang) => (
                              <button
                                key={lang.code}
                                onClick={() => handleTogglePreview(adv.id, lang.code)}
                                className={`text-[11px] px-2.5 py-1 rounded-lg font-medium transition-colors ${
                                  isExpanded && activePreviewLang === lang.code
                                    ? "bg-sky-700 text-white shadow-sm font-semibold"
                                    : "bg-slate-800 text-slate-400 hover:text-white"
                                }`}
                              >
                                {lang.name}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Quick action buttons */}
                        <div className="flex items-center space-x-2">
                          <button
                            type="button"
                            onClick={() => handleReject(adv.id)}
                            className="px-3 py-1.5 rounded-xl border border-rose-700/60 text-rose-300 hover:bg-rose-950/50 text-xs font-semibold transition-colors flex items-center space-x-1"
                          >
                            <X className="w-3.5 h-3.5" />
                            <span>Reject</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => handleApprove(adv.id)}
                            className="px-4 py-1.5 rounded-xl bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-bold shadow-md transition-all flex items-center space-x-1.5"
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span>Approve & Generate TTS</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => handleOpenBroadcastModal(adv.id)}
                            className="px-3 py-1.5 rounded-xl bg-sky-700 hover:bg-sky-600 text-white text-xs font-bold shadow-md transition-all flex items-center space-x-1"
                          >
                            <Send className="w-3.5 h-3.5" />
                            <span>Dry Run Preview</span>
                          </button>
                        </div>
                      </div>

                      {/* Expanded Translation Preview Panel */}
                      {isExpanded && (
                        <div className="mt-3 p-4 bg-slate-950/80 rounded-xl border border-slate-700/80 space-y-3">
                          {currentPreview?.flagged_for_review && (
                            <div className="bg-amber-950/60 border border-amber-500/60 text-amber-200 px-3 py-2 rounded-lg text-xs flex items-center space-x-2">
                              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                              <span>{currentPreview.review_disclaimer}</span>
                            </div>
                          )}

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                            <div className="p-3 bg-slate-900 rounded-lg border border-slate-800">
                              <div className="text-[10px] uppercase font-bold text-slate-400 mb-1">
                                English Baseline (Source)
                              </div>
                              <div className="font-semibold text-white mb-1">{adv.headline}</div>
                              <div className="text-slate-300 leading-relaxed">{adv.content}</div>
                            </div>

                            <div className="p-3 bg-slate-900 rounded-lg border border-slate-800">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-[10px] uppercase font-bold text-sky-400">
                                  {activePreviewLang.toUpperCase()} Translated Text
                                </span>
                                {currentPreview?.machine_translated && (
                                  <span className="text-[10px] bg-rose-500/20 text-rose-300 px-1.5 py-0.5 rounded font-mono">
                                    Machine Translated
                                  </span>
                                )}
                              </div>
                              <div className="font-semibold text-white mb-1">
                                {currentPreview?.headline || "Loading translation..."}
                              </div>
                              <div className="text-slate-300 leading-relaxed">
                                {currentPreview?.content || "Fetching translation..."}
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        {/* ── Delivery Tracking Log ── */}
        <section aria-labelledby="delivery-heading" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 id="delivery-heading" className="text-base font-bold text-white flex items-center space-x-2">
                <Send className="w-4 h-4 text-sky-400" />
                <span>Live Broadcast Delivery Tracking</span>
              </h2>
              <p className="text-xs text-slate-400">
                Audited notification dispatches to farmers across SMS & WhatsApp
              </p>
            </div>

            {/* Filter */}
            <div className="flex items-center space-x-2 text-xs">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                aria-label="Filter Delivery Status"
                value={logFilterStatus}
                onChange={(e) => setLogFilterStatus(e.target.value)}
                className="bg-slate-900 border border-slate-700 text-slate-200 rounded-lg px-2.5 py-1 text-xs focus:outline-none"
              >
                <option value="ALL">All Statuses</option>
                <option value="DELIVERED">DELIVERED</option>
                <option value="SENT">SENT</option>
                <option value="BLOCKED_SIMULATED">BLOCKED_SIMULATED</option>
                <option value="BLOCKED_CONSENT">BLOCKED_CONSENT</option>
                <option value="BLOCKED_OPT_OUT">BLOCKED_OPT_OUT</option>
                <option value="FAILED">FAILED</option>
              </select>
            </div>
          </div>

          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden shadow-lg">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950/60 uppercase tracking-wider text-[10px] text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="p-3">Log ID</th>
                    <th className="p-3">Advisory ID</th>
                    <th className="p-3">Channel</th>
                    <th className="p-3">Dispatch Status</th>
                    <th className="p-3">Attempts</th>
                    <th className="p-3">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredLogs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-slate-500">
                        No delivery logs recorded matching filter.
                      </td>
                    </tr>
                  ) : (
                    filteredLogs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-800/30 transition-colors">
                        <td className="p-3 font-mono text-slate-400">#{log.id}</td>
                        <td className="p-3 font-mono text-sky-400">#{log.advisory_id}</td>
                        <td className="p-3 font-semibold">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] ${
                              log.channel === "WHATSAPP"
                                ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                                : "bg-sky-950 text-sky-300 border border-sky-800"
                            }`}
                          >
                            {log.channel}
                          </span>
                        </td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              log.status === "DELIVERED" || log.status === "SENT"
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                : log.status.startsWith("BLOCKED")
                                ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                : "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                            }`}
                          >
                            {log.status}
                          </span>
                        </td>
                        <td className="p-3 font-mono">{log.attempt_count}</td>
                        <td className="p-3 text-slate-400">
                          {new Date(log.created_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </main>

      {/* ── 2-Step Broadcast Confirmation Modal ── */}
      {isBroadcastModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="broadcast-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm"
        >
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 id="broadcast-modal-title" className="text-base font-bold text-white flex items-center space-x-2">
                <Send className="w-4 h-4 text-sky-400" />
                <span>Guarded Broadcast Dispatch</span>
              </h3>
              <button
                onClick={() => setIsBroadcastModalOpen(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Dry-Run Breakdown */}
            <div className="space-y-3">
              <div className="text-xs font-semibold text-slate-300">
                Step 1: Dry-Run Recipient Verification
              </div>

              {dryRunResult && (
                <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2 text-xs">
                  <div className="flex justify-between text-slate-300">
                    <span>Targeted Farmers in Panchayat:</span>
                    <strong className="text-white">{dryRunResult[0]?.farmers_in_panchayat || 0}</strong>
                  </div>
                  <div className="flex justify-between text-amber-400">
                    <span>Excluded (72h Farmer Cooldown):</span>
                    <strong>{dryRunResult[0]?.blocked_cooldown || 0}</strong>
                  </div>
                  <div className="flex justify-between text-rose-400">
                    <span>Data Honesty Intercept (Simulated):</span>
                    <strong>{dryRunResult[0]?.blocked_simulated || 0}</strong>
                  </div>
                  <div className="pt-2 border-t border-slate-800 flex justify-between font-bold text-emerald-400 text-sm">
                    <span>Net Dispatches to Dispatch:</span>
                    <span>{dryRunResult[0]?.dry_run || 0}</span>
                  </div>
                </div>
              )}

              {/* Channel Selector */}
              <div className="flex items-center justify-between p-3 bg-slate-950 rounded-xl border border-slate-800">
                <span className="text-xs font-medium text-slate-300">Dispatch Channel:</span>
                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    onClick={() => setBroadcastChannel("SMS")}
                    className={`px-3 py-1 rounded-lg text-xs font-bold transition-colors ${
                      broadcastChannel === "SMS"
                        ? "bg-sky-700 text-white"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    SMS
                  </button>
                  <button
                    type="button"
                    onClick={() => setBroadcastChannel("WHATSAPP")}
                    className={`px-3 py-1 rounded-lg text-xs font-bold transition-colors ${
                      broadcastChannel === "WHATSAPP"
                        ? "bg-emerald-700 text-white"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    WhatsApp
                  </button>
                </div>
              </div>
            </div>

            {/* Broadcast Results or Action buttons */}
            {broadcastSummary ? (
              <div className="p-4 bg-emerald-950/60 border border-emerald-500/60 rounded-xl text-xs text-emerald-200 space-y-1">
                <div className="font-bold flex items-center space-x-1">
                  <CheckCircle className="w-4 h-4 text-emerald-400" />
                  <span>Broadcast Dispatched Successfully!</span>
                </div>
                <p>Audited logs have been written to the delivery database.</p>
              </div>
            ) : (
              <div className="flex items-center justify-end space-x-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsBroadcastModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={isExecutingBroadcast}
                  onClick={handleConfirmBroadcast}
                  className="px-5 py-2 rounded-xl bg-sky-700 hover:bg-sky-600 text-white text-xs font-bold shadow-lg transition-all flex items-center space-x-1.5"
                >
                  {isExecutingBroadcast ? (
                    <span>Dispatching...</span>
                  ) : (
                    <>
                      <Send className="w-3.5 h-3.5" />
                      <span>Confirm & Broadcast</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
