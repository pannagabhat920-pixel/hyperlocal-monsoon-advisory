import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const { access_token } = await req.json();
    if (!access_token) {
      return NextResponse.json({ error: "Missing token" }, { status: 400 });
    }

    const res = NextResponse.json({ ok: true });
    res.cookies.set("pannaga_session", access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 7, // 7 days
      path: "/",
    });

    return res;
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.delete("pannaga_session");
  return res;
}
