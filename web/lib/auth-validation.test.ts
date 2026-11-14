import { describe, expect, it } from "vitest";

import { validateSignup } from "./auth-validation";

describe("signup validation", () => {
  it("accepts a valid email and matching long password", () => {
    expect(
      validateSignup({
        email: "merchant@example.com",
        password: "correct horse battery",
        confirmPassword: "correct horse battery",
      }),
    ).toEqual({});
  });

  it("rejects invalid email", () => {
    expect(
      validateSignup({
        email: "not-an-email",
        password: "correct horse battery",
        confirmPassword: "correct horse battery",
      }).email,
    ).toBeTruthy();
  });

  it("rejects passwords shorter than 12 characters", () => {
    expect(
      validateSignup({
        email: "merchant@example.com",
        password: "shortpass",
        confirmPassword: "shortpass",
      }).password,
    ).toBeTruthy();
  });

  it("rejects mismatched passwords", () => {
    expect(
      validateSignup({
        email: "merchant@example.com",
        password: "correct horse battery",
        confirmPassword: "different horse battery",
      }).confirmPassword,
    ).toBeTruthy();
  });
});
