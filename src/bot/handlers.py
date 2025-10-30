"""Aiogram handlers for bot commands and the generation FSM."""

from __future__ import annotations

from typing import Any

from aiogram import Bot, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .callbacks import CategoryCallback, ConfirmationCallback, ParameterCallback, PromptCallback
from .constants import DEFAULT_CATEGORIES, PARAMETER_PRESETS, PROMPTS_BY_CATEGORY
from .exceptions import BackendError, GenerationError, InvalidFileError
from .fsm import GenerationStates
from .keyboards import (
    category_keyboard,
    confirmation_keyboard,
    main_menu_keyboard,
    parameter_keyboard,
    prompt_keyboard,
)
from .models import GenerationRequest, GenerationUpdate, format_history
from .services import BackendClient, GenerationService
from .validators import validate_image


def _extract_user_id(entity: Message | CallbackQuery) -> int | None:
    user = getattr(entity, "from_user", None)
    return getattr(user, "id", None)


class CoreCommandHandlers:
    """Handlers for simple commands that call REST APIs."""

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    def register(self, router: Router) -> None:
        router.message.register(self.start, Command("start"))
        router.message.register(self.menu, Command("menu"))
        router.message.register(self.profile, Command("profile"))
        router.message.register(self.subscribe, Command("subscribe"))
        router.message.register(self.history, Command("history"))
        router.message.register(self.balance, Command("balance"))
        router.message.register(self.help, Command("help"))

    async def start(self, message: Message, bot: Bot) -> None:
        await message.answer(
            "👋 Welcome! I'm here to help you orchestrate AI image generations."
        )
        await message.answer(
            "Use the menu below or type a command to get started.",
            reply_markup=main_menu_keyboard(),
        )
        # Ensure commands are visible even if the bot restarts mid-chat.
        from .commands import setup_bot_commands  # Local import to avoid cycles

        await setup_bot_commands(bot)

    async def menu(self, message: Message) -> None:
        await message.answer(
            "Here are the available actions:", reply_markup=main_menu_keyboard()
        )

    async def profile(self, message: Message) -> None:
        user_id = _extract_user_id(message)
        if user_id is None:
            await message.answer("Unable to determine your Telegram ID.")
            return
        try:
            profile = await self._backend.get_profile(user_id)
        except BackendError as exc:
            await message.answer(f"⚠️ Failed to load profile: {exc}")
            return
        await message.answer(profile.to_message(), parse_mode="HTML")

    async def history(self, message: Message) -> None:
        user_id = _extract_user_id(message)
        if user_id is None:
            await message.answer("Unable to determine your Telegram ID.")
            return
        try:
            history = await self._backend.get_history(user_id)
        except BackendError as exc:
            await message.answer(f"⚠️ Failed to load history: {exc}")
            return
        await message.answer(format_history(history), parse_mode="HTML")

    async def balance(self, message: Message) -> None:
        user_id = _extract_user_id(message)
        if user_id is None:
            await message.answer("Unable to determine your Telegram ID.")
            return
        try:
            balance = await self._backend.get_balance(user_id)
        except BackendError as exc:
            await message.answer(f"⚠️ Failed to load balance: {exc}")
            return
        await message.answer(balance.to_message(), parse_mode="HTML")

    async def subscribe(self, message: Message) -> None:
        user_id = _extract_user_id(message)
        if user_id is None:
            await message.answer("Unable to determine your Telegram ID.")
            return
        try:
            status = await self._backend.subscribe(user_id)
        except BackendError as exc:
            await message.answer(f"⚠️ Subscription failed: {exc}")
            return
        await message.answer(status.to_message(), parse_mode="HTML")

    async def help(self, message: Message) -> None:
        help_text = (
            "ℹ️ <b>How to use the bot</b>\n"
            "• /profile – View your account details\n"
            "• /generate – Launch the guided generation wizard\n"
            "• /history – Review recent generations\n"
            "• /balance – Check remaining credits\n"
            "• /subscribe – Manage your subscription plan\n"
            "Need assistance? Reply in this chat and our team will follow up."
        )
        await message.answer(help_text, parse_mode="HTML")


class GenerationHandlers:
    """FSM handlers for the multi-step generation flow."""

    def __init__(self, backend: BackendClient, generation_service: GenerationService) -> None:
        self._backend = backend
        self._service = generation_service

    def register(self, router: Router) -> None:
        router.message.register(self.cmd_generate, Command("generate"))
        router.message.register(
            self.on_photo,
            StateFilter(GenerationStates.waiting_for_photo),
        )
        router.callback_query.register(
            self.on_category_selected,
            CategoryCallback.filter(),
            StateFilter(GenerationStates.waiting_for_category),
        )
        router.callback_query.register(
            self.on_prompt_selected,
            PromptCallback.filter(),
            StateFilter(GenerationStates.waiting_for_prompt),
        )
        router.callback_query.register(
            self.on_parameter_selected,
            ParameterCallback.filter(),
            StateFilter(GenerationStates.waiting_for_parameters),
        )
        router.callback_query.register(
            self.on_confirmation,
            ConfirmationCallback.filter(),
            StateFilter(GenerationStates.waiting_for_confirmation),
        )

    async def cmd_generate(self, message: Message, state: FSMContext) -> None:
        await state.set_state(GenerationStates.waiting_for_photo)
        await message.answer(
            "📤 Please upload a reference image (JPEG/PNG, up to 10 MB)."
        )

    async def on_photo(self, message: Message, state: FSMContext) -> None:
        document = getattr(message, "document", None)
        photo_sizes = getattr(message, "photo", None)
        file_name: str | None = None
        file_id: str | None = None
        mime_type: str | None = None
        file_size: int | None = None

        if document is not None:
            file_name = getattr(document, "file_name", None)
            file_id = getattr(document, "file_id", None)
            mime_type = getattr(document, "mime_type", None)
            file_size = getattr(document, "file_size", None)
        elif photo_sizes:
            photo = photo_sizes[-1]
            file_id = getattr(photo, "file_id", None)
            file_size = getattr(photo, "file_size", None)
            mime_type = "image/jpeg"
        else:
            await message.answer("Please send a JPEG or PNG image to continue.")
            return

        if not file_id:
            await message.answer("Unable to read the uploaded file. Please try again.")
            return

        try:
            validate_image(file_name=file_name, file_size=file_size, mime_type=mime_type)
        except InvalidFileError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(
            photo_file_id=file_id,
            photo_file_name=file_name,
            photo_file_size=file_size,
        )
        await state.set_state(GenerationStates.waiting_for_category)
        await message.answer(
            "Great! Select a category to guide the generation.",
            reply_markup=category_keyboard(DEFAULT_CATEGORIES),
        )

    async def on_category_selected(
        self,
        callback: CallbackQuery,
        callback_data: CategoryCallback,
        state: FSMContext,
    ) -> None:
        await callback.answer()
        category = callback_data.value
        await state.update_data(category=category)
        await state.set_state(GenerationStates.waiting_for_prompt)
        prompts = PROMPTS_BY_CATEGORY.get(
            category, ["Describe the scene you would like to create."]
        )
        await callback.message.answer(
            f"Category <b>{category}</b> selected. Pick a prompt to continue:",
            reply_markup=prompt_keyboard(category, prompts),
            parse_mode="HTML",
        )

    async def on_prompt_selected(
        self,
        callback: CallbackQuery,
        callback_data: PromptCallback,
        state: FSMContext,
    ) -> None:
        await callback.answer()
        prompt = callback_data.value
        await state.update_data(prompt=prompt)
        await state.set_state(GenerationStates.waiting_for_parameters)
        await callback.message.answer(
            "Choose the rendering preset that best matches your needs:",
            reply_markup=parameter_keyboard(),
        )

    async def on_parameter_selected(
        self,
        callback: CallbackQuery,
        callback_data: ParameterCallback,
        state: FSMContext,
    ) -> None:
        await callback.answer()
        preset_key = callback_data.value
        preset = PARAMETER_PRESETS.get(preset_key)
        if not preset:
            await callback.message.answer("Unknown preset selected. Please try again.")
            return
        await state.update_data(
            parameter_key=preset_key,
            parameters=preset["settings"],
            parameter_label=preset.get("title", preset_key.title()),
        )
        await state.set_state(GenerationStates.waiting_for_confirmation)
        data = await state.get_data()
        summary = self._format_summary(data)
        await callback.message.answer(
            summary,
            reply_markup=confirmation_keyboard(),
            parse_mode="HTML",
        )

    async def on_confirmation(
        self,
        callback: CallbackQuery,
        callback_data: ConfirmationCallback,
        state: FSMContext,
    ) -> None:
        await callback.answer()
        if callback_data.action == "restart":
            await state.set_state(GenerationStates.waiting_for_photo)
            await callback.message.answer("Alright, send a new image to start over.")
            return

        data = await state.get_data()
        user_id = _extract_user_id(callback)
        if user_id is None:
            await callback.message.answer("Unable to determine your Telegram ID.")
            await state.clear()
            return

        request = GenerationRequest(
            category=str(data.get("category")),
            prompt=str(data.get("prompt")),
            parameters=dict(data.get("parameters", {})),
            source_file_id=str(data.get("photo_file_id")),
            source_file_name=data.get("photo_file_name"),
        )
        await state.set_state(GenerationStates.displaying_result)
        progress_message = await callback.message.answer("🚀 Generation in progress…")

        async def _on_progress(update: GenerationUpdate) -> None:
            text = update.format_progress()
            await progress_message.edit_text(text)

        try:
            result = await self._service.execute_generation(
                user_id, request, progress_callback=_on_progress
            )
        except GenerationError as exc:
            await progress_message.edit_text(f"❌ Generation failed: {exc}")
            await state.set_state(GenerationStates.waiting_for_photo)
            return
        await progress_message.edit_text("✅ Generation complete!")
        await callback.message.answer(result.to_message(), parse_mode="HTML")
        await state.clear()

    @staticmethod
    def _format_summary(data: dict[str, Any]) -> str:
        preset_label = data.get("parameter_label", "Custom")
        lines = ["🧾 <b>Review your configuration</b>"]
        lines.append(f"Category: {data.get('category')}")
        lines.append(f"Prompt: {data.get('prompt')}")
        lines.append(f"Preset: {preset_label}")
        return "\n".join(lines)


def create_bot_router(
    backend: BackendClient,
    generation_service: GenerationService,
) -> Router:
    router = Router(name="core_commands")
    core = CoreCommandHandlers(backend)
    core.register(router)
    generation_handlers = GenerationHandlers(backend, generation_service)
    generation_handlers.register(router)
    return router
