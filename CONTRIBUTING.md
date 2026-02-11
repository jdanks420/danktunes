# Contributing to danktunes

We welcome contributions from the community! Here's how you can help:

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/danktunes.git
   cd danktunes
   ```

3. **Set up your development environment**:
   ```bash
   # Install system dependencies
   sudo apt install mpg123 alsa-utils ffmpeg
   
   # Optional: tomli for Python < 3.11
   pip install tomli
   ```

## Development Guidelines

### Code Style
- Follow PEP 8 style guidelines
- Use meaningful variable and function names
- Add comments for complex logic
- Keep functions small and focused

### Testing
- Test your changes thoroughly
- Check that the player works with different audio formats
- Verify playlist functionality

### Documentation
- Update README.md if you add new features
- Document any configuration changes
- Add examples if needed

## Making Changes

1. **Create a new branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** and test them

3. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add feature: your description"
   ```

4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request** on GitHub

## Feature Requests

If you have ideas for new features:
1. Check the TODO.md file to see if it's already planned
2. Open an issue to discuss your idea
3. Consider implementing it yourself and submitting a PR

## Bug Reports

When reporting bugs:
1. Describe the issue clearly
2. Include steps to reproduce
3. Provide your system information
4. Share any error messages

## Code Review Process

1. Maintainers will review your PR
2. You may be asked to make changes
3. Once approved, your changes will be merged

## Community Guidelines

- Be respectful and inclusive
- Provide constructive feedback
- Help others when you can
- Follow the Code of Conduct

## License

By contributing, you agree that your contributions will be licensed under the MIT License.