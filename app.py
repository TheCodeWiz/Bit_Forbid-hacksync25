
import streamlit as st
from supabase import create_client, Client
import os
import re
from dotenv import load_dotenv
from datetime import datetime
import uuid
import google.generativeai as genai
import time

# Constants remain the same
EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
SAKHI_IMAGE_PATH = "sakhi_logo-wout-bg.png"

# Initialize Gemini with retry logic
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

SYSTEM_PROMPT = """You are SAKHI AI, a compassionate and understanding AI assistant focused on mental health and well-being. 
Your goal is to provide supportive, empathetic responses while maintaining appropriate boundaries and encouraging professional help when needed."""

# Questionnaire Configuration remains the same
QUESTIONS_CONFIG = {
    "AGE": {
        "options": ["Less than 20", "21-35", "36-50", "51 or more"],
        "type": "categorical"
    },
    "GENDER": {
        "options": ["Male", "Female"],
        "type": "categorical"
    }
}

# Add numeric questions
DEFAULT_QUESTIONS = [
    "BMI_RANGE", "SUFFICIENT_INCOME", "DONATION", "Fruit and Veggies",
    "DAILY_STRESS", "CORE_CIRCLE", "SUPPORTING_OTHERS", "SOCIAL_NETWORK",
    "ACHIEVEMENT", "TODO_COMPLETED", "FLOW", "DAILY_STEPS", "LIVE_VISION",
    "SLEEP_HOURS", "LOST_VACATION", "DAILY_SHOUTING", "PERSONAL_AWARDS",
    "TIME_FOR_PASSION", "WEEKLY_MEDITATION"
]

for question in DEFAULT_QUESTIONS:
    QUESTIONS_CONFIG[question] = {
        "options": list(range(11)),
        "type": "numeric"
    }

class GeminiHandler:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-pro')
        self.chat = self.model.start_chat(history=[])
        self.setup_context()
        self.max_retries = 3
        self.retry_delay = 1  # seconds

    def setup_context(self):
        try:
            self.chat.send_message(SYSTEM_PROMPT)
        except Exception as e:
            print(f"Error setting up context: {e}")

    def get_response(self, user_message):
        retries = 0
        while retries < self.max_retries:
            try:
                response = self.chat.send_message(user_message)
                return response.text
            except Exception as e:
                retries += 1
                if retries == self.max_retries:
                    return f"I apologize, but I'm currently experiencing technical difficulties. Please try again in a few moments."
                time.sleep(self.retry_delay * retries)

class SupabaseClient:
    def __init__(self):
        load_dotenv()
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.validate_credentials()
        self.client = create_client(self.url, self.key)

    def validate_credentials(self):
        if not self.url or not self.key:
            st.error("Supabase credentials are missing. Check your .env file.")
            st.stop()

    def login(self, email, password):
        try:
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            return response
        except Exception as e:
            raise Exception(f"Login failed: {str(e)}")

    def signup(self, email, password):
        try:
            response = self.client.auth.sign_up({
                "email": email,
                "password": password
            })
            return response
        except Exception as e:
            raise Exception(f"Signup failed: {str(e)}")

    def check_questionnaire_completion(self, user_id):
        try:
            response = self.client.table("questionnaire_responses") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Error checking questionnaire completion: {e}")
            return False

    def save_questionnaire_response(self, user_id, responses):
        try:
            data = {
                "user_id": user_id,
                "responses": responses,
                "timestamp": datetime.utcnow().isoformat()
            }
            self.client.table("questionnaire_responses").insert(data).execute()
            return True
        except Exception as e:
            print(f"Error saving questionnaire response: {e}")
            return False

    def save_chat_message(self, user_id, message, role):
        try:
            data = {
                "user_id": user_id,
                "message": message,
                "role": role,
                "timestamp": datetime.utcnow().isoformat(),
                "message_id": str(uuid.uuid4())
            }
            self.client.table("chat_messages").insert(data).execute()
            return True
        except Exception as e:
            print(f"Error saving chat message: {e}")
            return False

    def get_chat_history(self, user_id, limit=50):
        try:
            response = self.client.table("chat_messages") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("timestamp", desc=False) \
                .limit(limit) \
                .execute()
            return response.data
        except Exception as e:
            print(f"Error fetching chat history: {e}")
            return []

class AuthUI:
    def __init__(self, client):
        self.client = client

    def render(self):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(SAKHI_IMAGE_PATH, width=400)
            st.markdown("""
                <h1 style="text-align: center; font-family: 'Georgia', serif; 
                font-size: 32px; font-weight: bold; margin-top: 4px; color: #fff;">
                    Welcome to SAKHI AI
                </h1>
                """, unsafe_allow_html=True)
            
            login_tab, signup_tab = st.tabs(["Login", "Sign Up"])
            
            with login_tab:
                self.render_login_form()
            
            with signup_tab:
                self.render_signup_form()

    def render_login_form(self):
        st.subheader("Login to Your Account")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login", key="login_btn"):
            self.handle_login(email, password)

    def render_signup_form(self):
        st.subheader("Create a New Account")
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_password")
        
        if st.button("Sign Up", key="signup_btn"):
            self.handle_signup(email, password)

    def handle_login(self, email, password):
        if not email or not password:
            st.warning("Please enter both email and password.")
            return

        try:
            response = self.client.login(email, password)
            if response and response.user:
                # Check if user has completed questionnaire
                has_completed = self.client.check_questionnaire_completion(response.user.id)
                
                st.session_state.update({
                    "logged_in": True,
                    "user_id": response.user.id,
                    "email": email,
                    "questionnaire_completed": has_completed
                })
                st.success(f"Welcome back, {email}!")
                st.rerun()
        except Exception as e:
            st.error(str(e))

    def handle_signup(self, email, password):
        if not email or not password:
            st.warning("Please enter both email and password.")
            return
        if not re.match(EMAIL_REGEX, email):
            st.error("Please enter a valid email address.")
            return

        try:
            response = self.client.signup(email, password)
            if response and response.user:
                st.success("Account created! Please check your email for verification.")
            else:
                st.error("Signup failed. Please try again with a different email.")
        except Exception as e:
            st.error(str(e))

class QuestionnaireUI:
    def __init__(self, client):
        self.client = client
        self.questions = list(QUESTIONS_CONFIG.keys())

    def render_question(self, question):
        st.subheader(f"{question}:")
        config = QUESTIONS_CONFIG[question]
        response = st.radio(
            "",
            config["options"],
            index=None,
            key=f"radio_{question}"
        )
        
        if response is not None:
            st.session_state["responses"][question] = response

    def render(self):
        if "current_question" not in st.session_state:
            st.session_state.current_question = 0
            st.session_state.responses = {}

        current_index = st.session_state.current_question
        self.render_question(self.questions[current_index])

        # Navigation buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            if current_index > 0:
                if st.button("Previous"):
                    st.session_state.current_question -= 1
                    st.rerun()

        with col2:
            if current_index < len(self.questions) - 1:
                if st.button("Next"):
                    if self.questions[current_index] not in st.session_state.responses:
                        st.error("Please select an option before proceeding.")
                    else:
                        st.session_state.current_question += 1
                        st.rerun()
            else:
                if st.button("Submit"):
                    self.handle_submit()

    def handle_submit(self):
        if len(st.session_state.responses) == len(self.questions):
            if self.client.save_questionnaire_response(
                st.session_state.user_id,
                st.session_state.responses
            ):
                st.session_state.questionnaire_completed = True
                st.success("Questionnaire submitted successfully!")
                st.session_state.responses = {}
                st.session_state.current_question = 0
                time.sleep(2)  # Give user time to see success message
                st.rerun()
            else:
                st.error("Failed to submit questionnaire. Please try again.")
        else:
            st.error("Please answer all questions before submitting.")

class ChatUI:
    def __init__(self, supabase_client):
        self.supabase_client = supabase_client
        self.gemini_handler = GeminiHandler()

    def render_message(self, message, is_user=False):
        message_container = st.container()
        with message_container:
            if is_user:
                st.write(
                    f'<div style="display: flex; justify-content: flex-end;">'
                    f'<div style="background-color: #007AFF; color: white; padding: 10px 15px; '
                    f'border-radius: 15px; margin: 5px; max-width: 70%; word-wrap: break-word;">'
                    f'{message}</div></div>',
                    unsafe_allow_html=True
                )
            else:
                st.write(
                    f'<div style="display: flex; justify-content: flex-start;">'
                    f'<div style="background-color: #F0F0F0; color: black; padding: 10px 15px; '
                    f'border-radius: 15px; margin: 5px; max-width: 70%; word-wrap: break-word;">'
                    f'{message}</div></div>',
                    unsafe_allow_html=True
                )

    def render(self):
        st.markdown("""
            <style>
            .stTextInput>div>div>input {
                border-radius: 20px;
            }
            .stButton>button {
                border-radius: 20px;
                background-color: #007AFF;
                color: white;
            }
            </style>
            """, unsafe_allow_html=True)

        # Display chat history
        chat_history = self.supabase_client.get_chat_history(st.session_state.user_id)
        for message in chat_history:
            self.render_message(message["message"], message["role"] == "user")

        # Chat input
        col1, col2 = st.columns([5, 1])
        with col1:
            user_input = st.text_input("Type your message...", key="chat_input")
        with col2:
            send_button = st.button("Send")

        if send_button and user_input:
            # Save user message
            if self.supabase_client.save_chat_message(
                st.session_state.user_id,
                user_input,
                "user"
            ):
                # Get AI response
                ai_response = self.gemini_handler.get_response(user_input)
                
                # Save AI response
                if self.supabase_client.save_chat_message(
                    st.session_state.user_id,
                    ai_response,
                    "assistant"
                ):
                    st.rerun()
                else:
                    st.error("Failed to save AI response. Please try again.")
            else:
                st.error("Failed to send message. Please try again.")

def main():
    st.set_page_config(page_title="SAKHI AI", layout="centered")
    
    # Initialize Supabase client
    supabase_client = SupabaseClient()
    
    if "logged_in" not in st.session_state:
        auth_ui = AuthUI(supabase_client)
        auth_ui.render()
    else:
        # Check if questionnaire is completed
        if not st.session_state.get("questionnaire_completed", False):
            st.title("Well-being Questionnaire")
            st.write("Please complete this questionnaire before accessing the chat.")
            questionnaire_ui = QuestionnaireUI(supabase_client)
            questionnaire_ui.render()
        else:
            st.title("Chat with SAKHI")
            chat_ui = ChatUI(supabase_client)
            chat_ui.render()

        # Logout button
        if st.button("Logout", key="logout_btn"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()

