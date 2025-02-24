import streamlit as st
from supabase import create_client, Client
import os
import re
from dotenv import load_dotenv
from datetime import datetime
import uuid
import requests
import speech_recognition as sr
import time
import json  # Import json module

# Constants
EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
SAKHI_IMAGE_PATH = "sakhi_logo-wout-bg.png"

# Initialize environment variables
load_dotenv()

# Questionnaire Configuration
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
        self.n8n_webhook_url = "https://hacksync.app.n8n.cloud/webhook/1c370d0b-2291-4ed4-a9de-e058373b93d4"

    def render_question(self, question):
        st.subheader(f"{question}:")
        config = QUESTIONS_CONFIG[question]
        if config["type"] == "categorical":
            response = st.radio(
                "",
                config["options"],
                index=None,
                key=f"radio_{question}"
            )
        elif config["type"] == "numeric":
            response = st.slider(
                "",
                min_value=min(config["options"]),
                max_value=max(config["options"]),
                key=f"slider_{question}"
            )
        
        if response is not None:
            st.session_state["responses"][question] = response

    def render(self):
        if "responses" not in st.session_state:
            st.session_state.responses = {}

        for question in self.questions:
            self.render_question(question)

        if st.button("Submit"):
            self.handle_submit()

    def handle_submit(self):
        if len(st.session_state.responses) == len(self.questions):
            if self.client.save_questionnaire_response(
                st.session_state.user_id,
                st.session_state.responses
            ):
                # Send responses to n8n webhook
                try:
                    response = requests.post(
                        self.n8n_webhook_url, 
                        json=st.session_state.responses, 
                        headers={"Content-Type": "application/json"}
                    )

                    if response.status_code == 200:
                        webhook_response = response.text  # Accept text response instead of JSON
                        st.session_state.recommendations = webhook_response  # Store full response as text
                        
                        st.session_state.questionnaire_completed = True
                        st.success("Questionnaire submitted successfully!")
                    else:
                        st.error(f"Failed to send responses to webhook. Status code: {response.status_code}")
                        st.error(f"Response content: {response.text}")  # Debugging purpose
                        return
                except Exception as e:
                    st.error(f"Error sending responses to webhook: {str(e)}")
                    return

                st.session_state.responses = {}
                st.session_state.current_question = 0
                time.sleep(2)  # Give user time to see success message
                st.rerun()
            else:
                st.error("Failed to submit questionnaire. Please try again.")
        else:
            st.error("Please answer all questions before submitting.")

    def display_ai_response(self):
        if "recommendations" in st.session_state:
            st.subheader("Your Personalized AI Analysis")
            st.write(st.session_state.recommendations)  # Show AI text as received

class ChatUI:
    def __init__(self, supabase_client):
        self.supabase_client = supabase_client
        self.n8n_webhook_url = "https://hacksync.app.n8n.cloud/webhook/2869ee04-29a7-401a-b7c7-e7277c3048e5"
        if "voice_input" not in st.session_state:
            st.session_state.voice_input = ""
        if "current_message" not in st.session_state:
            st.session_state.current_message = ""

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
            .chat-container {
                display: flex;
                flex-direction: column-reverse;
                height: calc(100vh - 200px);
                overflow-y: auto;
                padding-bottom: 60px;
            }
            .fixed-header {
                position: fixed;
                top: 0;
                width: 100%;
                background-color: white;
                z-index: 1000;
                padding: 10px 0;
            }
            .fixed-footer {
                position: fixed;
                bottom: 0;
                width: 100%;
                background-color: white;
                z-index: 1000;
                padding: 10px 0;
            }
            </style>
            """, unsafe_allow_html=True)

        # Fixed header
        st.markdown('<div class="fixed-header"><h2>Chat with SAKHI</h2></div>', unsafe_allow_html=True)

        # Display chat history
        if "chat_history" not in st.session_state:
            try:
                st.session_state.chat_history = self.supabase_client.get_chat_history(
                    st.session_state.user_id
                )
            except Exception as e:
                st.session_state.chat_history = []
                st.error(f"Failed to load chat history: {str(e)}")

        # Display messages
        with st.container():
            st.markdown('<div class="chat-container">', unsafe_allow_html=True)
            for message in st.session_state.chat_history:
                self.render_message(
                    message["message"],
                    message["role"] == "user"
                )
            st.markdown('</div>', unsafe_allow_html=True)

        # Fixed footer with voice input handling
        st.markdown('<div class="fixed-footer">', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
        
        with col1:
            # Use session state for input field
            if st.session_state.voice_input:
                st.session_state.current_message = st.session_state.voice_input
                user_input = st.text_input(
                    "Type your message...", 
                    value=st.session_state.current_message,
                    key="chat_input"
                )
                st.session_state.voice_input = ""  # Clear voice input after setting current message
            else:
                user_input = st.text_input(
                    "Type your message...", 
                    value=st.session_state.current_message,
                    key="chat_input"
                )
            st.session_state.current_message = user_input

        with col2:
            if st.button("Send"):
                if st.session_state.current_message.strip():
                    self.handle_send_message(st.session_state.current_message)
                    st.session_state.current_message = ""  # Clear the message after sending
                    st.rerun()
        
        with col3:
            if st.button("🎤 Voice"):
                self.handle_voice_chat()
        
        with col4:
            if st.button("Logout"):
                st.session_state.clear()
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

    def handle_send_message(self, user_input):
        try:
            # Save user message
            self.supabase_client.save_chat_message(
                st.session_state.user_id,
                user_input,
                "user"
            )
            
            # Send message to n8n Webhook
            response = requests.post(self.n8n_webhook_url, data={"message": user_input})

            if response.status_code == 200:
                ai_response = response.text
            else:
                ai_response = "Error connecting to AI Agent."

            # Save AI response
            self.supabase_client.save_chat_message(
                st.session_state.user_id,
                ai_response,
                "assistant"
            )
            
            # Update chat history
            st.session_state.chat_history = self.supabase_client.get_chat_history(
                st.session_state.user_id
            )
            st.rerun()
        except Exception as e:
            st.error(f"Failed to send message: {str(e)}")

    def handle_voice_chat(self):
        try:
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                st.info("Listening... Speak now.")
                audio = recognizer.listen(source, timeout=5)
                st.info("Processing speech...")

            text = recognizer.recognize_google(audio)
            st.session_state.voice_input = text
            st.rerun()
            
        except sr.WaitTimeoutError:
            st.error("No speech detected. Please try again.")
        except sr.UnknownValueError:
            st.error("Could not understand the audio. Please try again.")
        except sr.RequestError as e:
            st.error(f"Could not process the audio: {str(e)}")
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

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
        
        elif "recommendations" in st.session_state:
            st.title("SAKHI AI Analysis")
            
            # Display AI-generated Analysis (Stress Level + Recommendations together)
            st.subheader("Your Personalized AI Analysis")
            st.write(st.session_state.recommendations)  # Show AI text as received

            # Add a button to start chatting
            st.markdown("<br>", unsafe_allow_html=True)  # Add spacing
            if st.button("🗣 Talk with SAKHI...", key="start_chat_button"):
                st.session_state.show_chat = True  # Activate chat
            
        # Show chat only when user clicks the button
        if st.session_state.get("show_chat", False):
            st.title("Chat with SAKHI")
            chat_ui = ChatUI(supabase_client)
            chat_ui.render()

if __name__ == "__main__":
    main()
