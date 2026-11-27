"""بوت تيليجرام لغرفة التحميض.

ابعتله لينك يوتيوب أو فيسبوك، يرجعلك فيديو أو mp3.

التشغيل:
    set TELEGRAM_TOKEN=التوكن من BotFather
    set ALLOWED_USERS=123456789        (اختياري: ايدي حسابك، يفصل بينهم بفاصلة)
    python telegram_bot.py
"""
import os, re, glob, shutil, tempfile, asyncio, logging
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
ALLOWED_USERS = {int(x) for x in os.environ.get('ALLOWED_USERS', '').split(',') if x.strip().isdigit()}
TG_LIMIT = 49 * 1024 * 1024  # حد رفع البوتات في تيليجرام 50 ميجا
MAX_SECONDS = 20 * 60
ALLOWED = re.compile(r'https?://([\w-]+\.)*(youtube\.com|youtu\.be|facebook\.com|fb\.watch|fb\.com)/\S+', re.I)
LINKS = {}  # message_id -> url
SLOT = asyncio.Semaphore(2)


def ok_user(update: Update) -> bool:
    return not ALLOWED_USERS or (update.effective_user and update.effective_user.id in ALLOWED_USERS)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ok_user(update):
        return
    await update.message.reply_text('ابعتلي لينك يوتيوب أو فيسبوك، وهرجعلك فيديو أو mp3.')


async def on_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ok_user(update):
        return
    m = ALLOWED.search(update.message.text or '')
    if not m:
        await update.message.reply_text('اللينك مش يوتيوب ولا فيسبوك.')
        return
    LINKS[update.message.message_id] = m.group(0)
    if len(LINKS) > 500:
        LINKS.pop(next(iter(LINKS)))
    mid = update.message.message_id
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton('فيديو 720', callback_data=f'v720:{mid}'),
        InlineKeyboardButton('فيديو 360', callback_data=f'v360:{mid}'),
        InlineKeyboardButton('mp3', callback_data=f'mp3:{mid}'),
    ]])
    await update.message.reply_text('عايزه ازاي؟', reply_markup=kb)


def run_download(url: str, kind: str, tmp: str) -> str:
    opts = {
        'quiet': True, 'noplaylist': True, 'socket_timeout': 20,
        'max_filesize': TG_LIMIT,
        'match_filter': yt_dlp.utils.match_filter_func(f'duration < {MAX_SECONDS}'),
        'outtmpl': os.path.join(tmp, '%(title).80s.%(ext)s'),
    }
    if kind == 'mp3':
        opts.update(format='bestaudio/best',
                    postprocessors=[{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}])
    else:
        h = kind[1:]
        opts.update(format=f'bestvideo[height<={h}]+bestaudio/best[height<={h}]/best', merge_output_format='mp4')
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])
    files = glob.glob(os.path.join(tmp, '*'))
    if not files:
        raise ValueError('no file')
    return files[0]


async def on_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not ok_user(update):
        return
    kind, _, mid = q.data.partition(':')
    url = LINKS.get(int(mid)) if mid.isdigit() else None
    if not url or kind not in ('v720', 'v360', 'mp3'):
        await q.edit_message_text('ابعت اللينك تاني.')
        return
    if SLOT.locked():
        await q.edit_message_text('فيه تحميلين شغالين، جرب بعد شوية.')
        return
    await q.edit_message_text('جاري التحميل...')
    tmp = tempfile.mkdtemp()
    try:
        async with SLOT:
            f = await asyncio.to_thread(run_download, url, kind, tmp)
        if os.path.getsize(f) > TG_LIMIT:
            await q.edit_message_text('الملف أكبر من 50 ميجا، تيليجرام مش بيسمح. جرب جودة أقل أو mp3.')
            return
        with open(f, 'rb') as fh:
            if kind == 'mp3':
                await ctx.bot.send_audio(q.message.chat_id, fh, filename=os.path.basename(f))
            else:
                await ctx.bot.send_video(q.message.chat_id, fh, filename=os.path.basename(f), supports_streaming=True)
        await q.edit_message_text('تم.')
    except Exception:
        logging.exception('download failed')
        await q.edit_message_text('التحميل فشل. جرب لينك تاني.')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if not TOKEN:
        raise SystemExit('حط TELEGRAM_TOKEN الاول.')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(on_choice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_link))
    app.run_polling()


if __name__ == '__main__':
    main()
