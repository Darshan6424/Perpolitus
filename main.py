import os
import json
import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from datetime import datetime
from keep_alive import keep_alive

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Constants
EXAM_DATE = datetime(2025, 4, 24)  # Change this to your exam date
COUNTDOWN_CHANNEL_ID = 123456789  # Replace with your channel ID

# Load tasks from JSON
def load_tasks():
    try:
        with open('tasks.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

tasks = load_tasks()

# Save tasks to JSON
def save_tasks():
    with open('tasks.json', 'w') as f:
        json.dump(tasks, f, indent=4)

# Calculate days remaining until exam
def days_remaining():
    today = datetime.now()
    delta = EXAM_DATE - today
    return delta.days

# Progress bar generator
def progress_bar(current, max_val=1000, length=20):
    filled = int(length * current / max_val)
    return f"[{'█' * filled}{' ' * (length - filled)}] {current}/{max_val}"

# Send daily countdown message
async def send_countdown():
    days = days_remaining()
    try:
        channel = await bot.fetch_channel(COUNTDOWN_CHANNEL_ID)
        if days > 0:
            message = (
                f"⏳ **EXAM COUNTDOWN**: {days} days remaining until April 24, 2025!\n"
                f"{'🔥' if days <= 30 else '📚'} Keep working hard!"
            )
            await channel.send(message)
        elif days == 0:
            await channel.send("🎉 **EXAM DAY IS HERE!** Good luck today!")
        else:
            await channel.send("✅ Exams are over! Hope you did well!")
    except Exception as e:
        print(f"Couldn't send countdown: {e}")

# Check for overdue tasks
async def check_deadlines():
    now = datetime.now()
    for user_id, user_data in tasks.items():
        for task_id, task in user_data.get('tasks', {}).items():
            if not task['completed'] and task.get('deadline'):
                deadline = datetime.strptime(task['deadline'], '%Y-%m-%d')
                if deadline < now:
                    try:
                        user = await bot.fetch_user(int(user_id))
                        await user.send(f"⚠️ Task overdue: **{task['name']}** (was due {task['deadline']})")
                    except:
                        continue

# Bot events
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await bot.tree.sync()
    
    # Schedule daily checks (9 AM UTC)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_deadlines, CronTrigger(hour=9, minute=0))
    scheduler.add_job(send_countdown, CronTrigger(hour=8, minute=0))  # 8 AM UTC
    scheduler.start()

# Task command group
@bot.tree.command(name="task", description="Manage your tasks")
@app_commands.choices(sub_command=[
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="done", value="done"),
    app_commands.Choice(name="list", value="list"),
    app_commands.Choice(name="undo", value="undo")
])
@app_commands.describe(
    sub_command="Task action to perform",
    name="Name of the task (for add)",
    points="Point value (for add)",
    category="Task category (optional)",
    deadline="Deadline YYYY-MM-DD (optional)",
    task_id="Task ID (for done/undo)"
)
async def task_command(
    interaction: discord.Interaction,
    sub_command: str,
    name: str = None,
    points: int = None,
    category: str = None,
    deadline: str = None,
    task_id: str = None
):
    user_id = str(interaction.user.id)
    
    # Initialize user data if not exists
    if user_id not in tasks:
        tasks[user_id] = {
            "totalPoints": 0,
            "currentStreak": 0,
            "lastCompletedDate": None,
            "tasks": {}
        }
    
    if sub_command == "add":
        task_id = str(int(datetime.now().timestamp()))
        tasks[user_id]["tasks"][task_id] = {
            "name": name,
            "points": points,
            "category": category or "General",
            "deadline": deadline,
            "completed": False
        }
        await interaction.response.send_message(
            f"✅ Added task: **{name}** ({points} pts, {category or 'No category'})"
        )
    
    elif sub_command == "done":
        if task_id in tasks[user_id]["tasks"]:
            task = tasks[user_id]["tasks"][task_id]
            task["completed"] = True
            tasks[user_id]["totalPoints"] += task["points"]
            
            # Streak system
            today = datetime.now().strftime('%Y-%m-%d')
            last_date = tasks[user_id].get("lastCompletedDate")
            
            if last_date != today:
                if last_date and (datetime.strptime(today, '%Y-%m-%d') - datetime.strptime(last_date, '%Y-%m-%d')).days == 1:
                    tasks[user_id]["currentStreak"] += 1
                else:
                    tasks[user_id]["currentStreak"] = 1
                tasks[user_id]["lastCompletedDate"] = today
            
            await interaction.response.send_message(
                f"🎉 Task completed: **{task['name']}** (+{task['points']} pts)\n"
                f"🔥 Streak: {tasks[user_id]['currentStreak']} days"
            )
        else:
            await interaction.response.send_message("❌ Task not found", ephemeral=True)
    
    elif sub_command == "list":
        task_list = [
            f"`{tid}`: {task['name']} ({task['points']} pts, {task.get('category', 'General')})"
            f"{' - ⏰ Due: ' + task['deadline'] if task.get('deadline') else ''}"
            for tid, task in tasks[user_id]["tasks"].items()
            if not task["completed"]
        ]
        await interaction.response.send_message(
            "📝 **Your Tasks**\n" + "\n".join(task_list) if task_list else "No active tasks!"
        )
    
    elif sub_command == "undo":
        if task_id in tasks[user_id]["tasks"]:
            task = tasks[user_id]["tasks"][task_id]
            task["completed"] = False
            tasks[user_id]["totalPoints"] -= task["points"]
            await interaction.response.send_message(f"↩️ Undone task: **{task['name']}**")
        else:
            await interaction.response.send_message("❌ Task not found", ephemeral=True)
    
    save_tasks()

@bot.tree.command(name="stats", description="Check your progress")
async def stats(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in tasks:
        await interaction.response.send_message("You haven't added any tasks yet!")
        return
    
    user_data = tasks[user_id]
    await interaction.response.send_message(
        f"🏆 **Your Stats**\n"
        f"• Total points: **{user_data['totalPoints']}**\n"
        f"• Current streak: **{user_data['currentStreak']}** days\n"
        f"• Progress: {progress_bar(user_data['totalPoints'])}"
    )

@bot.tree.command(name="leaderboard", description="See top users")
async def leaderboard(interaction: discord.Interaction):
    sorted_users = sorted(
        tasks.items(),
        key=lambda x: x[1]["totalPoints"],
        reverse=True
    )[:10]
    
    leaderboard_text = "\n".join(
        f"{i+1}. <@{uid}>: {data['totalPoints']} pts"
        for i, (uid, data) in enumerate(sorted_users)
    )
    
    await interaction.response.send_message(
        "🏆 **Leaderboard**\n" + (leaderboard_text if sorted_users else "No data yet!")
    )

@bot.tree.command(name="countdown", description="Check days remaining until exam")
async def countdown(interaction: discord.Interaction):
    days = days_remaining()
    if days > 0:
        message = (
            f"⏳ **Exam Countdown**: {days} days remaining until April 24, 2025!\n"
            f"{'❗ Less than a month to go! fooking study' if days <= 30 else 'Keep up the good work!'}"
        )
    elif days == 0:
        message = " **IT'S fooking EXAM DAY!** Good luck!"
    else:
        message = "✅ Exams are over! Hope you did well!"
    
    await interaction.response.send_message(message)

@bot.tree.command(name="help", description="Show all commands and how to use them")
async def help_command(interaction: discord.Interaction):
    help_embed = discord.Embed(
        title="Perpolitus Help",
        description="Bruh use guide is below:",
        color=0x00ff00
    )
    
    help_embed.add_field(
        name="📝 Task Commands",
        value=(
            "`/task add name:\"Task name\" points:50 category:Work` - Add new task\n"
            "`/task list` - Show your active tasks\n"
            "`/task done id:TASK_ID` - Complete a task\n"
            "`/task undo id:TASK_ID` - Undo a completed task"
        ),
        inline=False
    )
    
    help_embed.add_field(
        name="📊 Progress Tracking",
        value=(
            "`/stats` - View your points and streak\n"
            "`/leaderboard` - See top users"
        ),
        inline=False
    )
    
    help_embed.add_field(
        name="⏳ Special Features",
        value=(
            "`/countdown` - Days until exam\n"
            "Automatic daily countdown messages\n"
            "Task deadlines and reminders\n"
            "Streak bonuses for daily completion"
        ),
        inline=False
    )
    
    help_embed.add_field(
        name="🎯 Point System",
        value=(
            "• Small tasks: 10-50 pts\n"
            "• Medium tasks: 50-100 pts\n"
            "• Large tasks: 100+ pts\n"
            "• 7-day streak bonus: 2x points on day 7"
        ),
        inline=False
    )
    
    help_embed.set_footer(text="Good luck with your studies!")
    
    await interaction.response.send_message(embed=help_embed)

# Run the bot
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)