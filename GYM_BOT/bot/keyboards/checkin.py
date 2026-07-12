from aiogram.utils.keyboard import InlineKeyboardBuilder


def trainer_checkins_keyboard(clients):

    builder = InlineKeyboardBuilder()


    for client in clients:

        builder.button(
            text=f"👤 {client.full_name}",
            callback_data=f"trainer_checkin:{client.id}"
        )


    builder.adjust(1)


    return builder.as_markup()



def checkin_answer_keyboard(checkin_id):

    builder = InlineKeyboardBuilder()


    builder.button(
        text="💬 Відповісти клієнту",
        callback_data=f"reply_checkin:{checkin_id}"
    )


    builder.button(
        text="⬅️ Назад",
        callback_data="back_checkins"
    )


    builder.adjust(1)


    return builder.as_markup()