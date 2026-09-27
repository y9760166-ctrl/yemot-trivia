import os
import requests
from flask import Flask, request, Response

app = Flask(__name__)

# הטוקן של ימות המשיח (הגדירו ב-Environment Variables במידת הצורך)
YEMOT_SYSTEM_TOKEN = os.environ.get("YEMOT_TOKEN", "083136585:456987")

def extract_dtmf(params):
    """
    חילוץ נקי של המקש שהוקש מכל הפרמטרים האפשריים
    """
    if params.get("ApiDTMF") is not None and str(params.get("ApiDTMF")).strip() != "":
        return str(params.get("ApiDTMF")).strip()
    if params.get("dtmf") is not None and str(params.get("dtmf")).strip() != "":
        return str(params.get("dtmf")).strip()
    return ""

def get_trivia_file_path(folder, q_num, item_type, ans_num):
    """
    נתיב הקובץ הפיזי בשלוחת הטריוויה
    שאלה 1: folder/001.wav
    תשובה 2 של שאלה 1: folder/001_2.wav
    """
    padded_q = f"{q_num:03d}"
    if item_type == 'question':
        return f"{folder}/{padded_q}.wav"
    else:
        return f"{folder}/{padded_q}_{ans_num}.wav"

def delete_file_from_yemot(file_path):
    """
    מחיקת קובץ משרתי ימות המשיח
    """
    if not YEMOT_SYSTEM_TOKEN:
        return
    try:
        url = f"https://www.call2all.co.il/ym/api/DeleteFile?token={requests.utils.quote(YEMOT_SYSTEM_TOKEN)}&what={requests.utils.quote('ivar:/' + file_path)}"
        requests.get(url, timeout=2)
    except Exception:
        pass

def response_read(messages, val_name, type_val, min_val, max_val, timeout, tap, valid_digits):
    """
    בניית פקודת read תקינה בלבד (ללא id_list_message שגרם לניתוק!)
    """
    return f"read={messages}={val_name},{type_val},{min_val},{max_val},{timeout},{tap},no,{valid_digits}"

def send_yemot_response(body_text):
    return Response(body_text, mimetype="text/plain; charset=utf-8")

def get_trivia_data_from_yemot(trivia_folder):
    """
    סריקה דינמית של השלוחה בשרת ימות המשיח לקבלת כמות השאלות המדויקת
    """
    questions = []

    # אם מוגדר טוקן תקין - סריקת הקבצים בשלוחה דרך ה-API
    if YEMOT_SYSTEM_TOKEN:
        try:
            url = f"https://www.call2all.co.il/ym/api/GetIVR2Dir?token={requests.utils.quote(YEMOT_SYSTEM_TOKEN)}&path={requests.utils.quote('ivar:/' + str(trivia_folder))}"
            res = requests.get(url, timeout=2.5).json()

            if res.get("responseStatus") == "OK" and "files" in res:
                files = res.get("files", [])
                q_dict = {}

                for f in files:
                    name = f.get("name", "")
                    if name.endswith(".wav"):
                        base_name = name[:-4]
                        if base_name.isdigit() and len(base_name) == 3:
                            q_id = int(base_name)
                            if q_id not in q_dict:
                                q_dict[q_id] = 0
                        elif "_" in base_name:
                            parts = base_name.split("_")
                            if len(parts) == 2 and parts[0].isdigit() and len(parts[0]) == 3 and parts[1].isdigit():
                                q_id = int(parts[0])
                                ans_id = int(parts[1])
                                q_dict[q_id] = max(q_dict.get(q_id, 0), ans_id)

                sorted_q_ids = sorted(q_dict.keys())
                for q_id in sorted_q_ids:
                    ans_count = q_dict[q_id] if q_dict[q_id] > 0 else 3
                    questions.append({"id": q_id, "answersCount": ans_count})
        except Exception as e:
            print(f"API Scan Error: {e}")

    # אם אין טוקן או שהשלוחה ריקה - ברירת מחדל של שאלה אחת
    if not questions:
        questions = [{"id": 1, "answersCount": 3}]

    return {"questions": questions}

def handle_select_question(dtmf, trivia_data, trivia_folder):
    total_questions = len(trivia_data["questions"])

    if dtmf == '*':
        return "id_list_message=t-תודה ושלום.&hangup=yes"

    if dtmf != '':
        try:
            selected_q = int(dtmf)
            if 1 <= selected_q <= total_questions:
                return build_select_item_prompt(selected_q, trivia_data, trivia_folder)
        except ValueError:
            pass

    prompt_list = [
        "t-נמצאו",
        f"n-{total_questions}",
        "t-שאלות להיום. אנא בחרו את מספר השאלה לניהול"
    ]

    valid_digits_list = ["*"]
    for i in range(1, total_questions + 1):
        prompt_list.append("t-לשאלה")
        prompt_list.append(f"n-{i}")
        prompt_list.append("t-הקישו")
        prompt_list.append(f"n-{i}")
        valid_digits_list.append(str(i))

    prompt_str = ".".join(prompt_list)
    valid_digits_str = ",".join(valid_digits_list)

    return response_read(prompt_str, "dtmf", "digits", 1, 1, 7, "b", valid_digits_str) + \
           f"&step=select_question&trivia_folder={trivia_folder}"

def build_select_item_prompt(q_num, trivia_data, trivia_folder):
    questions = trivia_data.get("questions", [])
    question = questions[q_num - 1] if 0 < q_num <= len(questions) else questions[0]
    total_answers = question.get("answersCount", 3)

    prompt_list = [
        "t-שאלה מספר",
        f"n-{q_num}",
        "t-בשאלה זו יש",
        f"n-{total_answers}",
        "t-תשובות. לעריכת הקלטת השאלה הקישו",
        "n-0"
    ]

    valid_digits_list = ["0", "*"]
    for i in range(1, total_answers + 1):
        prompt_list.append("t-לעריכת תשובה")
        prompt_list.append(f"n-{i}")
        prompt_list.append("t-הקישו")
        prompt_list.append(f"n-{i}")
        valid_digits_list.append(str(i))

    prompt_str = ".".join(prompt_list)
    valid_digits_str = ",".join(valid_digits_list)

    return response_read(prompt_str, "dtmf", "digits", 1, 1, 7, "b", valid_digits_str) + \
           f"&step=select_item&q_num={q_num}&trivia_folder={trivia_folder}"

def handle_select_item(dtmf, q_num, trivia_data, trivia_folder):
    questions = trivia_data.get("questions", [])
    question = questions[q_num - 1] if 0 < q_num <= len(questions) else None

    if not question:
        return handle_select_question('', trivia_data, trivia_folder)

    if dtmf == '*':
        return handle_select_question('', trivia_data, trivia_folder)

    total_answers = question.get("answersCount", 3)

    if dtmf != '':
        try:
            choice = int(dtmf)
            if choice == 0:
                return build_action_menu_prompt(q_num, 'question', 0, trivia_folder)
            elif 1 <= choice <= total_answers:
                return build_action_menu_prompt(q_num, 'answer', choice, trivia_folder)
        except ValueError:
            pass

    return build_select_item_prompt(q_num, trivia_data, trivia_folder)

def get_post_edit_prompt_text():
    return "t-לעריכה נוספת בשאלה זו הקישו 1, לבחירת שאלה אחרת לניהול הקישו 2, ליציאה הקישו 3"

def build_post_edit_prompt(q_num, trivia_folder):
    return response_read(get_post_edit_prompt_text(), "dtmf", "digits", 1, 1, 7, "b", "1,2,3,*") + \
           f"&step=post_edit_menu&q_num={q_num}&trivia_folder={trivia_folder}"

def build_action_menu_prompt(q_num, item_type, ans_num, trivia_folder):
    return response_read("m-1009", "dtmf", "digits", 1, 1, 7, "b", "1,2,3,4,*") + \
           f"&step=action_menu&q_num={q_num}&item_type={item_type}&ans_num={ans_num}&trivia_folder={trivia_folder}"

def handle_action_menu(dtmf, q_num, item_type, ans_num, trivia_data, trivia_folder):
    if dtmf == '*':
        return build_select_item_prompt(q_num, trivia_data, trivia_folder)

    file_path = get_trivia_file_path(trivia_folder, q_num, item_type, ans_num)

    if dtmf == '1':
        play_prompt = f"f-{file_path}.m-1009"
        return response_read(play_prompt, "dtmf", "digits", 1, 1, 7, "b", "1,2,3,4,*") + \
               f"&step=action_menu&q_num={q_num}&item_type={item_type}&ans_num={ans_num}&trivia_folder={trivia_folder}"

    elif dtmf == '2':
        return build_post_edit_prompt(q_num, trivia_folder)

    elif dtmf == '3':
        return response_read("t-אנא הקליטו את ההודעה לאחר הצליל, בסיום הקישו סולמית", "rec_file", "voice", 1, 10, 60, "b", "#") + \
               f"&save_file_path={file_path}&step=post_edit_menu&q_num={q_num}&trivia_folder={trivia_folder}"

    elif dtmf == '4':
        delete_file_from_yemot(file_path)
        return response_read("t-ההקלטה נמחקה בהצלחה." + get_post_edit_prompt_text(), "dtmf", "digits", 1, 1, 7, "b", "1,2,3,*") + \
               f"&step=post_edit_menu&q_num={q_num}&trivia_folder={trivia_folder}"

    else:
        return build_action_menu_prompt(q_num, item_type, ans_num, trivia_folder)

def handle_post_edit_menu(dtmf, q_num, trivia_data, trivia_folder):
    if dtmf == '1':
        return build_select_item_prompt(q_num, trivia_data, trivia_folder)
    elif dtmf == '2':
        return handle_select_question('', trivia_data, trivia_folder)
    elif dtmf == '3' or dtmf == '*':
        return "id_list_message=t-תודה רבה. היציאה בוצעה בהצלחה.&hangup=yes"

    return build_post_edit_prompt(q_num, trivia_folder)

@app.route('/api/trivia', methods=['GET', 'POST'])
def trivia_endpoint():
    try:
        params = {}
        if request.args:
            params.update(request.args.to_dict())
        if request.is_json and request.json:
            params.update(request.json)
        elif request.form:
            params.update(request.form.to_dict())

        step = params.get('step', 'init')
        q_num = int(params.get('q_num', 0))
        item_type = params.get('item_type', '')
        ans_num = int(params.get('ans_num', 0))
        trivia_folder = params.get('trivia_folder', '1')

        dtmf = extract_dtmf(params)
        trivia_data = get_trivia_data_from_yemot(trivia_folder)

        if not trivia_data or not trivia_data.get('questions'):
            return send_yemot_response("id_list_message=t-לא נמצאו הקלטות טריוויה עבור היום. להתראות.&hangup=yes")

        response_text = ""

        if step in ['init', 'select_question']:
            response_text = handle_select_question(dtmf, trivia_data, trivia_folder)
        elif step == 'select_item':
            response_text = handle_select_item(dtmf, q_num, trivia_data, trivia_folder)
        elif step == 'action_menu':
            response_text = handle_action_menu(dtmf, q_num, item_type, ans_num, trivia_data, trivia_folder)
        elif step == 'post_edit_menu':
            response_text = handle_post_edit_menu(dtmf, q_num, trivia_data, trivia_folder)
        else:
            response_text = handle_select_question('', trivia_data, trivia_folder)

        return send_yemot_response(response_text)

    except Exception as error:
        print(f"Error in Trivia API: {error}")
        return send_yemot_response("id_list_message=t-אירעה שגיאה במערכת הניהול.&hangup=yes")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)
