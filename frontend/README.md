`app.js`
- Stores variables and functions for buttons, inputs, pdf viewer
- Adds event listeners to run JS functions when certain index.html elements are updated
- Defines functions that make calls to the backend 

How `async` works: 
- `fetch()` returns a Promise
- `await fetch()` awaits for the Promise to resolve. 
  - Use `await` when you want the result of a promise before continuing
- You can only use `await` inside an `async` function
- `async` functions always return a Promise
  - Use `async` when the code needs to wait for something external
- Without async/await, you'd have to write `.then(...)` chains
- Most other code is synchronous, updating the DOM or local state.



Functions in `app.js` that are async:
- initializeYearFilter() is async because it fetches /search-metadata
- openRandomIssue() is async because it fetches /random-document
- runSearch() is async because it fetches /search