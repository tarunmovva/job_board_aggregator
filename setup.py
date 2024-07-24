from setuptools import setup, find_packages

setup(
    name="job_board_aggregator",
    version="0.1.0",
    packages=find_packages(),    install_requires=[
        "requests>=2.28.0",
        "rich>=12.0.0",
        "typing-extensions>=4.4.0",
        "transformers>=4.30.0",
        "peft>=0.6.0",
        "torch>=1.13.0",
        "pinecone>=5.0.0",
        "pdfminer.six>=20221105",
        "python-docx>=0.8.11",
        "numpy>=1.23.0",
        "scikit-learn>=1.0.0",
        "pytz>=2023.3",
    ],
    entry_points={
        "console_scripts": [
            "job-aggregator=job_board_aggregator.cli:main",
        ],
    },
    python_requires=">=3.7",
    author="ST_MOVVA",
    author_email="stmovva@gmail.com",
    description="A tool to aggregate jobs from company job board APIs and match them with resumes",
)