from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import yt_dlp
import os
from urllib.parse import urlparse
from pytube import YouTube
import requests
import time

# Replace with your bot token
TOKEN = os.getenv('BOT_TOKEN', 'your_default_token_here')
# Изменяем путь к файлу cookies для работы в Docker
COOKIES_FILE = 'youtube_cookies.txt'  # Относительный путь

# Настройка прокси (если нужно)
#os.environ['HTTP_PROXY'] = 'http://your-proxy:port'
#os.environ['HTTPS_PROXY'] = 'https://your-proxy:port'

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command""" 
    await update.message.reply_text('Hello! I am a YouTube video downloader bot. Send me a YouTube video link and I will help you download it.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /help command"""
    help_text = "How to use this bot:"
    help_text += "1. Send me a YouTube video link"
    help_text += "2. Choose the video quality you want to download"
    help_text += "3. Wait for the download to complete"
    help_text += "Commands:"
    help_text += "/start - Start the bot"
    help_text += "/help - Show this help message"
    await update.message.reply_text(help_text)

def is_youtube_url(urls):
    """Check if the URL is a valid YouTube URL"""
    parsed = urlparse(urls)
    return 'youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    
    if not ("youtube.com" in url or "youtu.be" in url):
        await update.message.reply_text("❌ Пожалуйста, отправьте корректную ссылку на видео YouTube")
        return

    try:
        # Используем yt-dlp для получения информации о видео
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
        context.user_data['last_url'] = url
        context.user_data['video_info'] = info
        
        # Создаем кнопки для доступных форматов
        keyboard = [
            [InlineKeyboardButton("720p", callback_data="720")],
            [InlineKeyboardButton("480p", callback_data="480")],
            [InlineKeyboardButton("360p", callback_data="360")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎥 *{info['title']}*\n\n"
            f"👤 Автор: {info['uploader']}\n"
            f"⏱ Длительность: {int(info['duration']/60)}:{info['duration']%60:02d}\n\n"
            "Выберите качество видео для скачивания:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    except Exception as e:
        error_message = f"❌ Ошибка при обработке видео:\n{str(e)}\nТип ошибки: {type(e).__name__}"
        print(error_message)
        await update.message.reply_text(error_message)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        url = context.user_data.get('last_url')
        quality = query.data
        last_update_time = 0

        if not url:
            await query.message.reply_text("❌ Ошибка: URL не найден. Пожалуйста, отправьте ссылку заново.")
            return

        status_message = await query.message.reply_text("⏳ Подготовка к загрузке...")

        # Создаем функцию для обновления прогресса
        async def progress_hook(d):
            if d['status'] == 'downloading':
                try:
                    nonlocal last_update_time
                    current_time = time.time()
                    
                    if current_time - last_update_time < 10:
                        return
                        
                    total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    downloaded = d.get('downloaded_bytes', 0)
                    
                    if total_bytes:
                        percentage = (downloaded / total_bytes) * 100
                        speed = d.get('speed', 0)
                        if speed:
                            speed_mb = speed / 1024 / 1024
                            progress_text = (
                                f"⏳ Загрузка: {percentage:.1f}%\n"
                                f"📥 Скорость: {speed_mb:.1f} MB/s"
                            )
                        else:
                            progress_text = f"⏳ Загрузка: {percentage:.1f}%"
                        
                        await status_message.edit_text(progress_text)
                        last_update_time = current_time
                        
                except Exception as e:
                    print(f"Error updating progress: {e}")

        # Настраиваем yt-dlp для скачивания с прогрессом
        ydl_opts = {
            'format': f'best[height<={quality}]/bestvideo[height<={quality}]+bestaudio',
            'merge_output_format': 'mp4',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': True,
            'progress_hooks': [lambda d: context.application.create_task(progress_hook(d))],
            'postprocessor_hooks': [lambda d: print(f"Postprocessing: {d['status']}")],
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'prefer_ffmpeg': True,
            'keepvideo': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await status_message.edit_text("⏳ Получение информации о видео...")
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        # Проверяем существование файла
        if not os.path.exists(file_path):
            await status_message.edit_text("❌ Ошибка: файл не найден после загрузки")
            return

        # Отправляем видео
        await status_message.edit_text("📤 Отправка видео в Telegram...")
        
        with open(file_path, 'rb') as video_file:
            await query.message.reply_video(
                video=video_file,
                caption=f"📹 {info['title']}\nКачество: {quality}p",
                supports_streaming=True
            )
        
        # Удаляем временный файл
        if os.path.exists(file_path):
            os.remove(file_path)
            
        await status_message.edit_text("✅ Загрузка завершена!")

    except Exception as e:
        error_message = f"❌ Произошла ошибка при скачивании:\n{str(e)}"
        print(error_message)
        await query.message.reply_text(error_message)

def main():
    """Start the bot"""
   
    # Create downloads directory if it doesn't exist
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
        
    # Check if cookies file exists
    if not os.path.exists(COOKIES_FILE):
        print(f"Warning: Cookies file '{COOKIES_FILE}' not found. Some videos may be inaccessible.")

    # Create the Application and pass it your bot's token
    app = Application.builder().token(TOKEN).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    
    # Add message handler for YouTube links
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    # Add callback handler for download buttons
    app.add_handler(CallbackQueryHandler(button))

    # Start the bot
    print("Bot is running...")
    app.run_polling(poll_interval=1)

if __name__ == '__main__':
    main()